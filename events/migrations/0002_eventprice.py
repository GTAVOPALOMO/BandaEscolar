from django.db import migrations, models
import django.core.validators
import django.db.models.deletion

def seed_prices(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Price = apps.get_model("events", "EventPrice")
    for event in Event.objects.filter(has_tickets=True, ticket_price__gt=0).iterator():
        Price.objects.get_or_create(event_id=event.pk, name="General", defaults={"amount": event.ticket_price})

class Migration(migrations.Migration):
    dependencies = [("events", "0001_initial")]
    operations = [
        migrations.CreateModel(name="EventPrice", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID")),
            ("name", models.CharField(max_length=80)),
            ("amount", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
            ("is_active", models.BooleanField(default=True)),
            ("event", models.ForeignKey(to="events.event", on_delete=django.db.models.deletion.PROTECT, related_name="prices")),
        ]),
        migrations.AddConstraint(model_name="eventprice", constraint=models.UniqueConstraint(fields=("event","name"), name="unique_event_price_name")),
        migrations.RunPython(seed_prices, migrations.RunPython.noop),
    ]
