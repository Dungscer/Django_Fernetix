import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from django_fernetix import generate_key
from django_fernetix.operations import copy_field
from django_fernetix.rotation import rotate
from tests.testapp.models import Contact, Legacy, Secret

pytestmark = pytest.mark.django_db


def raw_column(table, column):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {table} ORDER BY id")
        return [row[0] for row in cursor.fetchall()]


def test_rotate_moves_rows_to_the_new_key():
    old, new = generate_key(), generate_key()
    with override_settings(DJANGO_FERNETIX_KEYS=[old]):
        Secret.objects.bulk_create([Secret(text=f"t{i}", number=i) for i in range(7)])
        Secret.objects.create()
    with override_settings(DJANGO_FERNETIX_KEYS=[new, old]):
        assert rotate(Secret, batch_size=3) == 8
    with override_settings(DJANGO_FERNETIX_KEYS=[new]):
        assert [s.text for s in Secret.objects.order_by("pk")][:7] == [f"t{i}" for i in range(7)]


def test_rotate_changes_the_ciphertext():
    Secret.objects.create(text="x")
    before = raw_column("testapp_secret", "text")
    call_command("fernet_rotate", "testapp.Secret")
    assert raw_column("testapp_secret", "text") != before


def test_rotate_rebuilds_blind_index_for_a_new_index_key():
    Contact.objects.create(email="a@example.com")
    with override_settings(DJANGO_FERNETIX_INDEX_KEY="another-key"):
        assert not Contact.objects.filter(email="a@example.com").exists()
        rotate(Contact)
        assert Contact.objects.filter(email="a@example.com").exists()


def test_command_selects_by_app_and_reports(capsys):
    Secret.objects.create(text="x")
    call_command("fernet_rotate", "testapp")
    out = capsys.readouterr().out
    assert "testapp.Secret: 1 rows" in out
    assert "testapp.Legacy: 0 rows" in out


def test_command_rejects_unknown_labels():
    with pytest.raises(CommandError):
        call_command("fernet_rotate", "nope.Missing")


def test_copy_field_encrypts_a_plain_column():
    Legacy.objects.bulk_create([Legacy(plain=f"p{i}") for i in range(5)] + [Legacy(plain=None)])
    operation = copy_field("testapp", "Legacy", "plain", "secret", batch_size=2)
    operation.code(apps, None)
    assert [l.secret for l in Legacy.objects.order_by("pk")] == [f"p{i}" for i in range(5)] + [None]
    assert not any(v and v.startswith("p") for v in raw_column("testapp_legacy", "secret"))


def test_copy_field_reverse_decrypts():
    for value in ("a", "b"):
        Legacy.objects.create(secret=value)
    copy_field("testapp", "Legacy", "plain", "secret").reverse_code(apps, None)
    assert raw_column("testapp_legacy", "plain") == ["a", "b"]
