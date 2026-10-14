"""Equality search over encrypted fields.

A field declared with ``blind_index=True`` gets a hidden companion column
holding an HMAC-SHA256 of its plain value. ``exact`` and ``in`` lookups on the
field are answered from that column; the encrypted column is never compared.
The companion reveals which rows share a value, which is the price of being
able to search.
"""
import hashlib
import hmac

from django.core.exceptions import EmptyResultSet, FieldError
from django.db import models

from .cipher import get_index_key


def compute_digest(label, text):
    message = label.encode() + b"\0" + text.encode()
    return hmac.new(get_index_key(), message, hashlib.sha256).hexdigest()


def make_companion():
    return models.CharField(max_length=64, null=True, editable=False, db_index=True)


class _BlindLookup(models.Lookup):
    prepare_rhs = False

    @property
    def field(self):
        return self.lhs.output_field

    def digest_of(self, value):
        if hasattr(value, "resolve_expression") or hasattr(value, "as_sql"):
            raise FieldError(
                "Blind index lookups accept plain values only, not expressions "
                "or subqueries."
            )
        return self.field.blind_digest(value)

    def index_column(self, compiler):
        target = self.lhs.target
        companion = target.model._meta.get_field(target.blind_index_name)
        return compiler.compile(companion.get_col(self.lhs.alias))


class BlindExact(_BlindLookup):
    lookup_name = "exact"

    def get_prep_lookup(self):
        return None if self.rhs is None else self.digest_of(self.rhs)

    def as_sql(self, compiler, connection):
        sql, params = self.index_column(compiler)
        return f"{sql} = %s", [*params, self.rhs]


class BlindIn(_BlindLookup):
    lookup_name = "in"

    def get_prep_lookup(self):
        return [self.digest_of(v) for v in self.rhs if v is not None]

    def as_sql(self, compiler, connection):
        if not self.rhs:
            raise EmptyResultSet
        sql, params = self.index_column(compiler)
        placeholders = ", ".join(["%s"] * len(self.rhs))
        return f"{sql} IN ({placeholders})", [*params, *self.rhs]


LOOKUPS = {"exact": BlindExact, "in": BlindIn}
