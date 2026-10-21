from django.urls import path
from . import views
urlpatterns = [path("", views.home, name="home"), path("eventos/<int:pk>/", views.event_detail, name="event_detail"), path("eventos/<int:pk>/imagen/", views.event_image, name="event_image"), path("gestion/eventos/", views.event_list, name="event_manage"), path("gestion/eventos/nuevo/", views.event_create, name="event_create"), path("gestion/eventos/<int:pk>/editar/", views.event_edit, name="event_edit"), path("gestion/eventos/<int:pk>/estado/", views.event_toggle, name="event_toggle")]
