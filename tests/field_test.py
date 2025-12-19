import pytest
from django.conf import settings
from django.db import models
from django.test import TestCase
from django_fernet.textfield import TextFernetField
from cryptography.fernet import Fernet

class SecretModel(models.Model):
    secret = TextFernetField()

    class Meta:
        app_label = "tests_app"

test_key = Fernet.generate_key()

settings.configure(
    INSTALLED_APPS=["tests_app"],
    ENCRYPTION_KEY=test_key,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)

import django
django.setup()

class TestEncryptedField(TestCase):
    def test_encryption_and_decryption(self):
        s = SecretModel(secret="secret data")
        s.save()
        s_from_db = SecretModel.objects.get(pk=s.pk)
        assert s_from_db.secret == "secret data"
        assert s_from_db.secret != s.secret

