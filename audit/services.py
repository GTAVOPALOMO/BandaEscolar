from .models import AuditLog

SENSITIVE = {"password", "token", "secret", "session"}

def _clean(value):
    if not isinstance(value, dict):
        return value
    return {k: ("[OCULTO]" if any(s in k.lower() for s in SENSITIVE) else v) for k, v in value.items()}

def log(*, actor, module, action, entity, entity_id="", result="OK", reason="", before=None, after=None, correlation_id=""):
    return AuditLog.objects.create(actor=actor if getattr(actor, "is_authenticated", False) else None,
        module=module, action=action, entity=entity, entity_id=str(entity_id), result=result,
        reason=reason, before=_clean(before or {}), after=_clean(after or {}), correlation_id=correlation_id)
