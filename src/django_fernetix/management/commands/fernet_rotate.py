from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from django_fernetix.rotation import fernet_fields, rotate


class Command(BaseCommand):
    help = (
        "Re-encrypt Fernet fields with the first key in DJANGO_FERNETIX_KEYS and "
        "rebuild blind indexes. Run it after putting a new key first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "models",
            nargs="*",
            help="app_label or app_label.ModelName; defaults to every model with Fernet fields.",
        )
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, models, batch_size, **options):
        selected = self.select(models)
        for model in selected:
            count = rotate(model, batch_size)
            self.stdout.write(f"{model._meta.label}: {count} rows")
        if not selected:
            self.stdout.write("No models with Fernet fields found.")

    def select(self, labels):
        if not labels:
            candidates = apps.get_models()
        else:
            candidates = []
            for label in labels:
                try:
                    if "." in label:
                        candidates.append(apps.get_model(label))
                    else:
                        candidates.extend(apps.get_app_config(label).get_models())
                except (LookupError, ValueError) as exc:
                    raise CommandError(f"Unknown model or app: {label}") from exc
        return [m for m in candidates if not m._meta.proxy and fernet_fields(m)]
