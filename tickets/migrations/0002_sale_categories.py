from django.db import migrations, models

def backfill(apps, schema_editor):
    Sale = apps.get_model("tickets", "TicketSale")
    Ticket = apps.get_model("tickets", "Ticket")
    for sale in Sale.objects.all().iterator():
        sale.price_breakdown = [{"price_id": None, "name": "General", "amount": sale.unit_price, "quantity": sale.quantity}]
        sale.save(update_fields=["price_breakdown"])
        Ticket.objects.filter(sale_id=sale.pk).update(category_name="General", sold_price=sale.unit_price)

class Migration(migrations.Migration):
    dependencies = [("tickets", "0001_initial"), ("events", "0002_eventprice")]
    operations = [
        migrations.AddField(model_name="ticketsale", name="price_breakdown", field=models.JSONField(default=list, blank=True)),
        migrations.AddField(model_name="ticket", name="category_name", field=models.CharField(max_length=80, blank=True)),
        migrations.AddField(model_name="ticket", name="sold_price", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
