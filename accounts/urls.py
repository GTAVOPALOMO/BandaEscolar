from django.urls import path
from . import views
urlpatterns = [path("", views.user_list, name="user_list"), path("nueva/", views.user_create, name="user_create"),
 path("<int:pk>/rol/", views.user_role, name="user_role"), path("<int:pk>/clave/", views.user_reset_password, name="user_reset_password"),
 path("<int:pk>/estado/", views.user_toggle, name="user_toggle")]
