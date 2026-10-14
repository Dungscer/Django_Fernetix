from django.db import models

from django_fernetix import (
    FernetDateField,
    FernetDateTimeField,
    FernetEmailField,
    FernetIntegerField,
    FernetJSONField,
    FernetTextField,
)


class Secret(models.Model):
    text = FernetTextField(null=True)
    short = FernetTextField(max_length=20, null=True)
    email = FernetEmailField(null=True)
    number = FernetIntegerField(null=True)
    day = FernetDateField(null=True)
    moment = FernetDateTimeField(null=True)
    data = FernetJSONField(null=True)


class Contact(models.Model):
    email = FernetEmailField(blind_index=True, ignore_case=True)
    phone = FernetTextField(blind_index=True, null=True)
    note = FernetTextField(null=True)


class Base(models.Model):
    tag = FernetTextField(blind_index=True)

    class Meta:
        abstract = True


class Child(Base):
    pass


class Owner(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)


class Legacy(models.Model):
    plain = models.TextField(null=True)
    secret = FernetTextField(null=True)
