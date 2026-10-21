from django.urls import path
from . import views
urlpatterns = [path("", views.cash_home, name="cash_home"), path("abrir/", views.cash_open, name="cash_open"), path("movimiento/", views.cash_movement, name="cash_movement"), path("movimiento/<int:pk>/corregir/", views.cash_correct, name="cash_correct"), path("cerrar/", views.cash_close, name="cash_close")]
