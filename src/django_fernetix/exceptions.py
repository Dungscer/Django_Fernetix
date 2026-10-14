class FernetError(Exception):
    """Base class for all django_fernetix errors."""


class DecryptionError(FernetError):
    """A stored value could not be decrypted.

    Either no configured key matches, the stored token is damaged, or the
    column holds data that was written before the field was encrypted.
    """
