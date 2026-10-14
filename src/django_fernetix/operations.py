from django.db import migrations

from .fields import FernetField
from .rotation import iter_instances


def _copy(apps, app_label, model_name, source, target, batch_size):
    model = apps.get_model(app_label, model_name)
    target_field = model._meta.get_field(target)
    update_fields = (
        target_field.update_field_names()
        if isinstance(target_field, FernetField)
        else [target]
    )
    for instance in iter_instances(model, batch_size):
        setattr(instance, target, getattr(instance, source))
        instance.save(update_fields=update_fields)


def copy_field(app_label, model_name, source, target, batch_size=500):
    """Migration operation that copies one column into another.

    Meant for encrypting an existing column: add a ``Fernet*`` field next to
    the plain one, run ``copy_field(app, model, "plain", "encrypted")``, then
    remove the plain field and rename the new one. Reversing the operation
    copies the values back.
    """

    def forward(apps, schema_editor):
        _copy(apps, app_label, model_name, source, target, batch_size)

    def backward(apps, schema_editor):
        _copy(apps, app_label, model_name, target, source, batch_size)

    return migrations.RunPython(forward, backward)
