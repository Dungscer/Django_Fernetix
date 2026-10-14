from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SETTING = "DJANGO_FERNETIX_KEYS"


def generate_key():
    """Return a new random key, ready to be put into ``DJANGO_FERNETIX_KEYS``."""
    return Fernet.generate_key().decode()


@lru_cache(maxsize=8)
def _build(keys):
    try:
        return MultiFernet([Fernet(key) for key in keys])
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"{SETTING} holds an invalid key; each one must be 32 url-safe "
            "base64-encoded bytes, see django_fernetix.generate_key()."
        ) from exc


def get_cipher():
    """Return the cipher for the current settings.

    The first key encrypts, any key decrypts. Settings are read on each call
    so keys are not frozen at import time.
    """
    keys = getattr(settings, SETTING, None)
    if isinstance(keys, (str, bytes)):
        keys = [keys]
    if not keys:
        raise ImproperlyConfigured(f"Set {SETTING} to use django_fernetix fields.")
    return _build(tuple(keys))


INDEX_SETTING = "DJANGO_FERNETIX_INDEX_KEY"


def get_index_key():
    """Secret that keys the blind indexes; unrelated to the encryption keys.

    It is kept apart from ``DJANGO_FERNETIX_KEYS`` so that rotating the
    encryption keys does not invalidate the indexes.
    """
    key = getattr(settings, INDEX_SETTING, None)
    if not key:
        raise ImproperlyConfigured(f"Set {INDEX_SETTING} to use blind_index=True.")
    return key.encode() if isinstance(key, str) else bytes(key)
