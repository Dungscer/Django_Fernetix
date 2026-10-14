import datetime
import zoneinfo

import pytest
from django import forms
from django.core import serializers
from django.core.exceptions import FieldError, ImproperlyConfigured, ValidationError
from django.db import connection, models
from django.test import override_settings
from django.test.utils import isolate_apps

from django_fernet import DecryptionError, FernetTextField, generate_key
from tests.testapp.models import Secret

pytestmark = pytest.mark.django_db


def raw(pk, column):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM testapp_secret WHERE id = %s", [pk])
        return cursor.fetchone()[0]


def roundtrip(**values):
    pk = Secret.objects.create(**values).pk
    return Secret.objects.get(pk=pk)


def test_value_is_encrypted_in_database():
    secret = Secret.objects.create(text="secret data")
    assert "secret data" not in raw(secret.pk, "text")
    assert Secret.objects.get(pk=secret.pk).text == "secret data"


@pytest.mark.parametrize(
    "field, value",
    [
        ("text", "héllo"),
        ("text", ""),
        ("short", "short"),
        ("email", "a@example.com"),
        ("number", -42),
        ("number", 2**70),
        ("day", datetime.date(2021, 10, 29)),
        ("data", {"a": [1, 2, {"b": None}], "c": "d"}),
        ("data", [1, 2, 3]),
        ("data", "just a string"),
        ("data", 0),
    ],
)
def test_roundtrip(field, value):
    assert getattr(roundtrip(**{field: value}), field) == value


def test_none_is_stored_as_null():
    secret = Secret.objects.create()
    assert raw(secret.pk, "text") is None
    assert Secret.objects.get(pk=secret.pk).text is None


def test_ciphertext_is_random():
    first = Secret.objects.create(text="same")
    second = Secret.objects.create(text="same")
    assert raw(first.pk, "text") != raw(second.pk, "text")


def test_column_is_plain_text():
    for name in ("text", "data", "moment", "number"):
        field = Secret._meta.get_field(name)
        assert field.db_type(connection) == models.TextField().db_type(connection)


def test_datetime_keeps_its_instant():
    berlin = datetime.datetime(
        2021, 10, 29, 3, 16, 6, 896068, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
    )
    loaded = roundtrip(moment=berlin).moment
    assert loaded.tzinfo is not None
    assert loaded == berlin


def test_datetime_save_twice_is_stable():
    secret = roundtrip(moment=datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc))
    moment = secret.moment
    secret.save()
    assert Secret.objects.get(pk=secret.pk).moment == moment


def test_naive_datetime_is_made_aware():
    loaded = roundtrip(moment=datetime.datetime(2021, 1, 1, 12, 0)).moment
    assert loaded.tzinfo is not None


def test_string_input_is_coerced():
    loaded = roundtrip(number="7", day="2021-10-29", moment="2021-10-29T01:02:03+00:00")
    assert loaded.number == 7
    assert loaded.day == datetime.date(2021, 10, 29)
    assert loaded.moment == datetime.datetime(2021, 10, 29, 1, 2, 3, tzinfo=datetime.timezone.utc)


def test_invalid_input_is_rejected():
    with pytest.raises(ValidationError):
        Secret.objects.create(number="abc")
    with pytest.raises(ValidationError):
        Secret.objects.create(day="not a date")


def test_bytes_are_stored_as_text():
    assert roundtrip(text=b"data").text == "data"


@pytest.mark.parametrize("lookup", ["exact", "iexact", "contains", "in", "gt", "startswith"])
def test_lookups_are_rejected(lookup):
    value = [""] if lookup == "in" else ""
    with pytest.raises(FieldError, match="cannot be queried"):
        list(Secret.objects.filter(**{f"email__{lookup}": value}))


def test_json_key_transform_is_rejected():
    with pytest.raises(FieldError, match="cannot be queried"):
        list(Secret.objects.filter(data__key="x"))


def test_isnull_lookup_works():
    Secret.objects.create(text="x")
    Secret.objects.create()
    assert Secret.objects.filter(text__isnull=True).count() == 1


@isolate_apps("tests.testapp")
@pytest.mark.parametrize("option", ["primary_key", "unique", "db_index"])
def test_unsupported_options_fail_the_system_check(option):
    class Broken(models.Model):
        value = FernetTextField(**{option: True})

        class Meta:
            app_label = "testapp"

    errors = Broken._meta.get_field("value").check()
    assert "django_fernet.E001" in [error.id for error in errors]


def test_wrong_key_raises_decryption_error():
    secret = Secret.objects.create(text="x")
    with override_settings(DJANGO_FERNET_KEYS=[generate_key()]):
        with pytest.raises(DecryptionError, match="testapp.Secret.text"):
            Secret.objects.get(pk=secret.pk)


def test_unencrypted_value_raises_decryption_error():
    secret = Secret.objects.create(text="x")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE testapp_secret SET text = %s WHERE id = %s", ["plain", secret.pk])
    with pytest.raises(DecryptionError):
        Secret.objects.get(pk=secret.pk)


def test_key_rotation():
    old, new = generate_key(), generate_key()
    with override_settings(DJANGO_FERNET_KEYS=[old]):
        pk = Secret.objects.create(text="x").pk
    with override_settings(DJANGO_FERNET_KEYS=[new, old]):
        secret = Secret.objects.get(pk=pk)
        assert secret.text == "x"
        secret.save()
    with override_settings(DJANGO_FERNET_KEYS=[new]):
        assert Secret.objects.get(pk=pk).text == "x"


def test_single_key_string_is_accepted():
    with override_settings(DJANGO_FERNET_KEYS=generate_key()):
        assert roundtrip(text="x").text == "x"


@pytest.mark.parametrize("keys", [None, [], ["too short"]])
def test_bad_key_configuration(keys):
    with override_settings(DJANGO_FERNET_KEYS=keys):
        with pytest.raises(ImproperlyConfigured):
            Secret.objects.create(text="x")


def test_max_length_validates_the_plain_value():
    with pytest.raises(ValidationError):
        Secret._meta.get_field("short").run_validators("x" * 21)
    Secret._meta.get_field("short").run_validators("x" * 20)


def test_email_validation():
    with pytest.raises(ValidationError):
        Secret._meta.get_field("email").run_validators("not an email")


def test_queryset_update_and_bulk_create_encrypt():
    Secret.objects.bulk_create([Secret(text="bulk")])
    Secret.objects.update(text="updated")
    secret = Secret.objects.get()
    assert secret.text == "updated"
    assert "updated" not in raw(secret.pk, "text")


def test_serialization_roundtrip():
    secret = Secret.objects.create(
        text="t", number=3, data={"a": 1}, moment=datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc)
    )
    dumped = serializers.serialize("json", [secret])
    assert "encrypted" not in dumped
    restored = next(serializers.deserialize("json", dumped)).object
    assert (restored.text, restored.number, restored.data) == ("t", 3, {"a": 1})
    assert restored.moment == secret.moment


def test_deconstruct():
    _, path, _, kwargs = Secret._meta.get_field("short").deconstruct()
    assert path == "django_fernet.fields.FernetTextField"
    assert kwargs == {"max_length": 20, "null": True}


def test_form_fields():
    assert isinstance(Secret._meta.get_field("email").formfield(), forms.EmailField)
    assert isinstance(Secret._meta.get_field("number").formfield(), forms.IntegerField)
    short = Secret._meta.get_field("short").formfield()
    assert short.max_length == 20
    assert isinstance(Secret._meta.get_field("text").formfield().widget, forms.Textarea)
    assert isinstance(Secret._meta.get_field("data").formfield(), forms.JSONField)
