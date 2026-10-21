from django.conf import settings
from django.db import models

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    module = models.CharField(max_length=30, db_index=True)
    action = models.CharField(max_length=60, db_index=True)
    entity = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=80, blank=True)
    result = models.CharField(max_length=20, default="OK")
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("La auditoría es inmutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("La auditoría es inmutable")
