from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path
from accounts.views import dashboard, ForcedPasswordChangeView, SecureLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", lambda request: JsonResponse({"status": "ok"})),
    path("ingresar/", SecureLoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cambiar-clave/", ForcedPasswordChangeView.as_view(), name="force_password_change"),
    path("panel/", dashboard, name="dashboard"),
    path("cuentas/", include("accounts.urls")), path("estudiantes/", include("students.urls")),
    path("cuotas/", include("dues.urls")), path("caja/", include("cash.urls")),
    path("", include("events.urls")), path("tickets/", include("tickets.urls")),
    path("auditoria/", include("audit.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
