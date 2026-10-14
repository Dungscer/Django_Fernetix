from .fields import FernetField


def fernet_fields(model):
    return [f for f in model._meta.concrete_fields if isinstance(f, FernetField)]


def iter_instances(model, batch_size=500):
    """Yield every row of ``model``, fetched in primary-key ordered batches.

    Batches (rather than one cursor) keep memory flat and allow writing while
    iterating, which some databases do not permit on an open cursor.
    """
    queryset = model._base_manager.order_by("pk")
    last_pk = None
    while True:
        batch = queryset if last_pk is None else queryset.filter(pk__gt=last_pk)
        rows = list(batch[:batch_size])
        if not rows:
            return
        yield from rows
        last_pk = rows[-1].pk


def rotate(model, batch_size=500):
    """Re-encrypt every Fernet field of ``model`` with the first configured key.

    Blind indexes are rebuilt as well, so this also applies a new
    ``DJANGO_FERNETIX_INDEX_KEY``. Returns the number of rows rewritten.
    Rows are saved with ``save(update_fields=...)``, so ``post_save`` fires.
    """
    fields = fernet_fields(model)
    if not fields:
        return 0
    update_fields = [name for field in fields for name in field.update_field_names()]
    count = 0
    for instance in iter_instances(model, batch_size):
        instance.save(update_fields=update_fields)
        count += 1
    return count
