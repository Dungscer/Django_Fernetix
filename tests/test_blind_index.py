import pytest
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import connection, models
from django.test import override_settings
from django.test.utils import isolate_apps

from django_fernetix import FernetJSONField, FernetTextField
from tests.testapp.models import Child, Contact, Owner

pytestmark = pytest.mark.django_db


def test_exact_lookup_finds_the_row():
    target = Contact.objects.create(email="a@example.com")
    Contact.objects.create(email="b@example.com")
    assert list(Contact.objects.filter(email="a@example.com")) == [target]
    assert Contact.objects.get(email="a@example.com").email == "a@example.com"


def test_no_match():
    Contact.objects.create(email="a@example.com")
    assert not Contact.objects.filter(email="other@example.com").exists()


def test_ignore_case():
    target = Contact.objects.create(email="Alice@Example.com")
    assert list(Contact.objects.filter(email="ALICE@example.COM")) == [target]


def test_case_sensitive_by_default():
    Contact.objects.create(email="x@example.com", phone="AbC")
    assert not Contact.objects.filter(phone="abc").exists()
    assert Contact.objects.filter(phone="AbC").exists()


def test_in_lookup():
    first = Contact.objects.create(email="a@example.com")
    second = Contact.objects.create(email="b@example.com")
    Contact.objects.create(email="c@example.com")
    found = Contact.objects.filter(email__in=["a@example.com", "b@example.com", None])
    assert set(found) == {first, second}
    assert not Contact.objects.filter(email__in=[]).exists()


def test_exact_none_means_isnull():
    Contact.objects.create(email="a@example.com", phone=None)
    assert Contact.objects.filter(phone=None).count() == 1


def test_companion_column_does_not_contain_plain_value():
    contact = Contact.objects.create(email="a@example.com")
    with connection.cursor() as cursor:
        cursor.execute("SELECT email_blind_index FROM testapp_contact WHERE id = %s", [contact.pk])
        digest = cursor.fetchone()[0]
    assert len(digest) == 64 and "example" not in digest


def test_other_lookups_stay_blocked():
    with pytest.raises(FieldError):
        list(Contact.objects.filter(email__contains="a"))


def test_related_lookup():
    contact = Contact.objects.create(email="a@example.com")
    owner = Owner.objects.create(contact=contact)
    assert list(Owner.objects.filter(contact__email="a@example.com")) == [owner]


def test_index_follows_changes():
    contact = Contact.objects.create(email="old@example.com")
    contact.email = "new@example.com"
    contact.save()
    assert not Contact.objects.filter(email="old@example.com").exists()
    assert Contact.objects.filter(email="new@example.com").exists()


def test_update_fields_with_companion_name():
    contact = Contact.objects.create(email="old@example.com")
    contact.email = "new@example.com"
    contact.save(update_fields=["email", "email_blind_index"])
    assert Contact.objects.filter(email="new@example.com").exists()


def test_bulk_create():
    Contact.objects.bulk_create([Contact(email="bulk@example.com")])
    assert Contact.objects.filter(email="bulk@example.com").exists()


def test_inherited_from_abstract_model():
    child = Child.objects.create(tag="red")
    assert list(Child.objects.filter(tag="red")) == [child]
    assert len([f for f in Child._meta.get_field("tag").model._meta.fields if f.name == "tag_blind_index"]) == 1


def test_digest_depends_on_the_field():
    field = Contact._meta.get_field("phone")
    other = Contact._meta.get_field("note")
    assert field.blind_digest("x") != Contact._meta.get_field("email").blind_digest("x")
    assert other.blind_index is False


def test_missing_index_key():
    with override_settings(DJANGO_FERNETIX_INDEX_KEY=None):
        errors = Contact._meta.get_field("email").check()
        assert "django_fernetix.E002" in [e.id for e in errors]
        with pytest.raises(ImproperlyConfigured):
            Contact.objects.create(email="a@example.com")


@isolate_apps("tests.testapp")
def test_json_does_not_support_blind_index():
    class Broken(models.Model):
        data = FernetJSONField(blind_index=True)

        class Meta:
            app_label = "testapp"

    errors = Broken._meta.get_field("data").check()
    assert "django_fernetix.E003" in [e.id for e in errors]


def test_deconstruct_keeps_options():
    _, _, _, kwargs = Contact._meta.get_field("email").deconstruct()
    assert kwargs["blind_index"] is True and kwargs["ignore_case"] is True
    assert FernetTextField().deconstruct()[3] == {}
