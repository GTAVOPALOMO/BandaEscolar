from django.urls import path
from . import views
urlpatterns = [path("", views.sale_list, name="sale_list"), path("vender/", views.sale_create, name="sale_create"), path("venta/<int:pk>/", views.sale_detail, name="sale_detail"), path("venta/<int:pk>/pdf/", views.sale_pdf, name="sale_pdf"), path("escanear/", views.scan, name="ticket_scan"), path("<int:pk>/anular/", views.ticket_void, name="ticket_void"), path("<int:pk>/reemplazar/", views.ticket_replace, name="ticket_replace")]
