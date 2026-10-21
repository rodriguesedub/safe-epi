from django.urls import path

from . import views

app_name = "alertas"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("executar/", views.executar, name="executar"),
    path("compras.csv", views.compras_csv, name="compras_csv"),
]
