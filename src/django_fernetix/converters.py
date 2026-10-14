"""Conversion between Python values and the text that gets encrypted.

Each codec is independent of the database backend: what is encrypted is
decided here, not by how the database would store the plain value.
"""
import datetime
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


def _invalid(kind, value):
    return ValidationError(f"{value!r} is not a valid {kind}.", code="invalid")


class TextCodec:
    def coerce(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).decode()
        return str(value)

    def dumps(self, value):
        return value

    def loads(self, text):
        return text


class IntegerCodec:
    def coerce(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise _invalid("integer", value) from None

    def dumps(self, value):
        return str(value)

    def loads(self, text):
        return int(text)


class DateCodec:
    def coerce(self, value):
        if isinstance(value, datetime.datetime):
            if timezone.is_aware(value):
                value = timezone.make_naive(value)
            return value.date()
        if isinstance(value, datetime.date):
            return value
        try:
            parsed = parse_date(str(value))
        except ValueError:
            parsed = None
        if parsed is None:
            raise _invalid("date", value)
        return parsed

    def dumps(self, value):
        return value.isoformat()

    def loads(self, text):
        return datetime.date.fromisoformat(text)


class DateTimeCodec:
    def coerce(self, value):
        if isinstance(value, datetime.datetime):
            result = value
        elif isinstance(value, datetime.date):
            result = datetime.datetime.combine(value, datetime.time.min)
        else:
            try:
                result = parse_datetime(str(value))
            except ValueError:
                result = None
            if result is None:
                raise _invalid("datetime", value)
        if settings.USE_TZ and timezone.is_naive(result):
            result = timezone.make_aware(result)
        return result

    def dumps(self, value):
        # Always store aware values as UTC so the offset survives the trip.
        if timezone.is_aware(value):
            value = value.astimezone(datetime.timezone.utc)
        return value.isoformat()

    def loads(self, text):
        value = datetime.datetime.fromisoformat(text)
        if settings.USE_TZ and timezone.is_naive(value):
            value = timezone.make_aware(value, datetime.timezone.utc)
        return value


class JSONCodec:
    def __init__(self, encoder=None, decoder=None):
        self.encoder = encoder
        self.decoder = decoder

    def coerce(self, value):
        return value

    def dumps(self, value):
        return json.dumps(value, cls=self.encoder)

    def loads(self, text):
        return json.loads(text, cls=self.decoder)
