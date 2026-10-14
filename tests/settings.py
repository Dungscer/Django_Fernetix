import os

from django_fernetix import generate_key

SECRET_KEY = "tests"
USE_TZ = True
INSTALLED_APPS = ["django_fernetix", "tests.testapp"]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
DJANGO_FERNETIX_KEYS = [generate_key()]

if os.environ.get("TEST_DB") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("PGDATABASE", "postgres"),
            "USER": os.environ.get("PGUSER", "postgres"),
            "PASSWORD": os.environ.get("PGPASSWORD", "postgres"),
            "HOST": os.environ.get("PGHOST", "localhost"),
            "PORT": os.environ.get("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DJANGO_FERNETIX_INDEX_KEY = "test-index-key"
