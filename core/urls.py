from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="sw"),
    path("offline/", views.offline, name="offline"),
    path("demo/iniciar/", views.demo_iniciar, name="demo_iniciar"),
]
