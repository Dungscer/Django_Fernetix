from cryptography.fernet import InvalidToken
from django import forms
from django.core import checks, validators
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import models

from . import blind_index, converters
from .cipher import INDEX_SETTING, get_cipher
from .exceptions import DecryptionError

__all__ = [
    "FernetField",
    "FernetTextField",
    "FernetEmailField",
    "FernetIntegerField",
    "FernetDateField",
    "FernetDateTimeField",
    "FernetJSONField",
]


class FernetField(models.Field):
    """Base for model fields that keep their value encrypted at rest.

    The Fernet token (url-safe base64, so plain ASCII) goes into a ``text``
    column. A subclass picks a codec, which defines how its Python value is
    turned into text before encryption, and a form field.
    """

    codec_class = None
    form_class = forms.CharField
    description = "Encrypted value"

    def __init__(self, *args, blind_index=False, **kwargs):
        self.blind_index = blind_index
        super().__init__(*args, **kwargs)
        self.codec = self.codec_class()

    def get_internal_type(self):
        return "TextField"

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.blind_index:
            kwargs["blind_index"] = True
        return name, path, args, kwargs

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        for option in ("primary_key", "unique", "db_index"):
            if getattr(self, option):
                errors.append(
                    checks.Error(
                        f"{self.__class__.__name__} cannot be used with {option}=True.",
                        hint="Encrypted values are random, so they can be neither "
                        "compared nor indexed.",
                        obj=self,
                        id="django_fernet.E001",
                    )
                )
        if self.blind_index:
            errors.extend(self._check_blind_index())
        return errors

    def _check_blind_index(self):
        from django.conf import settings

        if getattr(settings, INDEX_SETTING, None):
            return []
        return [
            checks.Error(
                f"blind_index=True needs the {INDEX_SETTING} setting.",
                obj=self,
                id="django_fernet.E002",
            )
        ]

    # Blind index: a hidden companion column that makes equality searchable

    @property
    def blind_index_name(self):
        return f"{self.name}_blind_index"

    def contribute_to_class(self, cls, name, private_only=False):
        super().contribute_to_class(cls, name, private_only=private_only)
        # Abstract models pass their fields on to subclasses, which add the
        # companion themselves; migration state models get it from the state.
        if self.blind_index and not cls._meta.abstract and cls.__module__ != "__fake__":
            cls.add_to_class(self.blind_index_name, blind_index.make_companion())

    def blind_text(self, value):
        """The canonical text that the blind index is computed from."""
        return self.codec.dumps(value)

    def blind_digest(self, value):
        label = f"{self.model._meta.label_lower}.{self.name}"
        return blind_index.compute_digest(label, self.blind_text(self.to_python(value)))

    def update_field_names(self):
        """Names to pass to ``save(update_fields=...)`` after changing this field."""
        names = [self.name]
        try:
            self.model._meta.get_field(self.blind_index_name)
        except FieldDoesNotExist:
            return names
        return names + [self.blind_index_name]

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        if self.blind_index:
            digest = None if value is None else self.blind_digest(value)
            setattr(model_instance, self.blind_index_name, digest)
        return value

    # Python value <-> database

    def to_python(self, value):
        return None if value is None else self.codec.coerce(value)

    def get_prep_value(self, value):
        return self.to_python(super().get_prep_value(value))

    def get_db_prep_value(self, value, connection, prepared=False):
        if not prepared:
            value = self.get_prep_value(value)
        if value is None:
            return None
        text = self.codec.dumps(value)
        return get_cipher().encrypt(text.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if not isinstance(value, str):
            value = bytes(value).decode()
        try:
            text = get_cipher().decrypt(value.encode()).decode()
        except InvalidToken:
            raise DecryptionError(
                f"Cannot decrypt {self.model._meta.label}.{self.name}: no key in "
                "DJANGO_FERNET_KEYS matches, or the stored value is not an "
                "encrypted token."
            ) from None
        return self.codec.loads(text)

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return None if value is None else self.codec.dumps(value)

    # Encrypted values cannot be searched

    def _not_queryable(self, name):
        return FieldError(
            f"Cannot use '{name}' on {self.__class__.__name__}: encrypted values "
            "cannot be queried, only isnull is supported (plus exact and in with blind_index=True)."
        )

    def get_lookup(self, lookup_name):
        if self.blind_index and lookup_name in blind_index.LOOKUPS:
            return blind_index.LOOKUPS[lookup_name]
        if lookup_name != "isnull":
            raise self._not_queryable(lookup_name)
        return super().get_lookup(lookup_name)

    def get_transform(self, lookup_name):
        raise self._not_queryable(lookup_name)

    # Forms

    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", self.form_class)
        return super().formfield(**kwargs)


class FernetTextField(FernetField):
    codec_class = converters.TextCodec

    def __init__(self, *args, max_length=None, ignore_case=False, **kwargs):
        self.ignore_case = ignore_case
        super().__init__(*args, max_length=max_length, **kwargs)
        if max_length is not None:
            self.validators.append(validators.MaxLengthValidator(max_length))

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.ignore_case:
            kwargs["ignore_case"] = True
        return name, path, args, kwargs

    def blind_text(self, value):
        text = super().blind_text(value)
        return text.casefold() if self.ignore_case else text

    def formfield(self, **kwargs):
        kwargs.setdefault("max_length", self.max_length)
        if self.max_length is None:
            kwargs.setdefault("widget", forms.Textarea)
        return super().formfield(**kwargs)


class FernetEmailField(FernetTextField):
    default_validators = [validators.validate_email]
    form_class = forms.EmailField

    def __init__(self, *args, max_length=254, **kwargs):
        super().__init__(*args, max_length=max_length, **kwargs)


class FernetIntegerField(FernetField):
    codec_class = converters.IntegerCodec
    form_class = forms.IntegerField


class FernetDateField(FernetField):
    codec_class = converters.DateCodec
    form_class = forms.DateField


class FernetDateTimeField(FernetField):
    codec_class = converters.DateTimeCodec
    form_class = forms.DateTimeField


class FernetJSONField(FernetField):
    form_class = forms.JSONField

    def __init__(self, *args, encoder=None, decoder=None, **kwargs):
        self.encoder = encoder
        self.decoder = decoder
        super().__init__(*args, **kwargs)

    def codec_class(self):
        return converters.JSONCodec(self.encoder, self.decoder)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.encoder is not None:
            kwargs["encoder"] = self.encoder
        if self.decoder is not None:
            kwargs["decoder"] = self.decoder
        return name, path, args, kwargs

    def value_to_string(self, obj):
        return self.value_from_object(obj)

    def _check_blind_index(self):
        return [
            checks.Error(
                "FernetJSONField does not support blind_index.",
                obj=self,
                id="django_fernet.E003",
            )
        ]

    def formfield(self, **kwargs):
        kwargs.setdefault("encoder", self.encoder)
        kwargs.setdefault("decoder", self.decoder)
        return super().formfield(**kwargs)
