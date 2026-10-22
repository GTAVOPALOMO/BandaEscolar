from django.urls import path
from . import views
urlpatterns = [path("tarifas/", views.rates, name="rates"), path("tarifas/<int:pk>/cancelar/", views.rate_cancel, name="rate_cancel"), path("estudiante/<int:student_pk>/abono/", views.payment_create, name="payment_create"),
 path("abono/<int:pk>/revertir/", views.payment_reverse, name="payment_reverse"), path("estudiante/<int:student_pk>/perdonar/", views.waive, name="waive"),
 path("perdon/<int:pk>/revertir/", views.waiver_reverse, name="waiver_reverse"), path("estudiante/<int:student_pk>/estado.pdf", views.statement_pdf, name="statement_pdf")]
