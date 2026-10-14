# django-fernetix

Django model fields that keep their values encrypted in the database using
[Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC).
Meant as a maintained alternative to the abandoned `django-fernet-fields`,
but with its own API and storage format. It does not read data written by
that package.

## Setup

```
pip install django-fernetix
```

Add `"django_fernetix"` to `INSTALLED_APPS` (needed for the `fernet_rotate`
command), then configure the keys:

```python
# settings.py
from django_fernetix import generate_key  # run once, keep the output secret

DJANGO_FERNETIX_KEYS = ["<key from generate_key()>"]
```

Keys must be real Fernet keys; nothing is derived from `SECRET_KEY`.
Losing every key means losing the data.

## Fields

```python
from django.db import models
from django_fernetix import FernetTextField, FernetJSONField

class Account(models.Model):
    iban = FernetTextField(max_length=34)
    notes = FernetTextField(null=True)
    profile = FernetJSONField(default=dict)
```

| Field | Python value |
|---|---|
| `FernetTextField(max_length=None)` | `str` |
| `FernetEmailField` | `str`, validated as an email |
| `FernetIntegerField` | `int` (any size) |
| `FernetDateField` | `datetime.date` |
| `FernetDateTimeField` | `datetime.datetime`, returned in UTC when `USE_TZ = True` |
| `FernetJSONField(encoder=, decoder=)` | anything JSON can hold |

Validators (`max_length`, email format, ...) run on the plain value.

## Key rotation

`DJANGO_FERNETIX_KEYS` is a list. The first key encrypts, every key decrypts.
To rotate: put the new key first, run

```
python manage.py fernet_rotate              # every model with Fernet fields
python manage.py fernet_rotate shop         # one app
python manage.py fernet_rotate shop.Account # one model
```

then remove the old key. The command re-saves rows in batches
(`--batch-size`), so `post_save` signals fire.

## Searching: blind index

Encrypted columns can't be queried, but equality search is possible with a
blind index: an HMAC of the plain value in a hidden companion column.

```python
# settings.py
DJANGO_FERNETIX_INDEX_KEY = "<another long random secret>"

class Customer(models.Model):
    email = FernetEmailField(blind_index=True, ignore_case=True)

Customer.objects.get(email="Alice@example.com")
Customer.objects.filter(email__in=[...])
```

* Only `exact` and `in` work. `ignore_case=True` (text fields) lowercases
  before hashing, so the match is case-insensitive.
* `blind_index=True` adds `<name>_blind_index` (an indexed `CharField`), which
  shows up in your migrations. Existing rows get `NULL` there until
  `fernet_rotate` has run.
* The index key is separate from the encryption keys on purpose: rotating
  encryption keys leaves the indexes valid. To change the index key, set the
  new one and run `fernet_rotate`; lookups miss until it finishes.
* The index tells an attacker with database access which rows share a value.
  That is the cost of searchability; leave it off for fields you don't search.
* The index is updated by `save()` and `bulk_create()`. It is **not** updated
  by `QuerySet.update()`, and `save(update_fields=[...])` must include
  `<name>_blind_index`. Run `fernet_rotate` to repair.
* Renaming the model or the field changes the digests; run `fernet_rotate`.
* Not available on `FernetJSONField`.

## How it works and what it can't do

* Every field stores its Fernet token in a `text` column, whatever the plain
  type is. Datetimes and JSON are serialized by the package itself, not by the
  database driver, so e.g. timezones and PostgreSQL `jsonb` are never involved.
* `None` is stored as `NULL`, everything else is encrypted.
* Tokens are random, so equal values look different. Therefore encrypted
  columns **cannot be queried or indexed**: every lookup except `isnull`
  raises `FieldError` (unless a blind index is enabled, see above), and `primary_key`, `unique` or `db_index` fail
  Django's system check (`django_fernetix.E001`). Lookups
  by encrypted email, as django-allauth does, need `blind_index=True`.
* A value that cannot be decrypted raises `DecryptionError` naming the model
  field.

### Existing plain columns

The encrypted column is separate, so convert in three migrations:

1. add `secret_enc = FernetTextField(null=True)`;
2. copy the data:

   ```python
   from django_fernetix.operations import copy_field

   operations = [copy_field("shop", "Account", "secret", "secret_enc")]
   ```

3. `RemoveField` the old column, `RenameField` `secret_enc` to `secret`.

`copy_field` is reversible (it copies the values back, decrypted).

### Hiding values in the admin

The admin shows decrypted values. To hide them:

```python
formfield_overrides = {
    FernetTextField: {"widget": forms.PasswordInput(render_value=False)},
}
```

## Development

```
pip install -e ".[test]"
pytest                    # sqlite
TEST_DB=postgres pytest   # needs PostgreSQL, configured via PG* variables
```

## License

MIT, see [LICENSE](LICENSE).
