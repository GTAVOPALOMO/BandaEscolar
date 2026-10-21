from django.urls import path
from . import views
urlpatterns = [path("", views.student_list, name="student_list"), path("nuevo/", views.student_create, name="student_create"),
 path("<int:pk>/", views.student_detail, name="student_detail"), path("<int:pk>/editar/", views.student_edit, name="student_edit"),
 path("<int:pk>/retirar/", views.student_withdraw, name="student_withdraw"), path("<int:pk>/reingresar/", views.student_reenroll, name="student_reenroll"),
 path("<int:pk>/encargado/", views.guardian_link, name="guardian_link"), path("<int:pk>/encargado/<int:link_pk>/quitar/", views.guardian_unlink, name="guardian_unlink")]
