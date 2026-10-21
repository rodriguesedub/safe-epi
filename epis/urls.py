from django.urls import path

from . import views

app_name = "epis"
urlpatterns = [
    path("", views.unidades, name="unidades"),
    path("meus/", views.meus_epis, name="meus"),
    path("entregar/", views.entrega_nova, name="entrega_nova"),
    path("entregar/unidades/", views.opcoes_unidades, name="opcoes_unidades"),
    path("<str:codigo>/", views.unidade_detalhe, name="unidade"),
]
