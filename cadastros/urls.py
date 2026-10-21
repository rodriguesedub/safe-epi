from django.urls import path

from . import views

app_name = "cadastros"
urlpatterns = [path("importar/", views.importar, name="importar")]
