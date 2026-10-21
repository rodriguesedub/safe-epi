from django.urls import path

from . import views

app_name = "relatorios"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("estatisticas/", views.estatisticas, name="estatisticas"),
    path("busca/", views.busca, name="busca"),
    path("colaboradores/<int:pk>/ficha-epi/", views.ficha_epi, name="ficha_epi"),
    path("colaboradores/<int:pk>/", views.trabalhador, name="trabalhador"),
    path("conformidade/", views.conformidade, name="conformidade"),
]
