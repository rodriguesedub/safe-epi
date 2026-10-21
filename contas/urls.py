from django.urls import path

from . import views

app_name = "contas"
urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="login"),
    path("sair/", views.sair, name="logout"),
    path("demo/<str:username>/", views.demo_entrar, name="demo_entrar"),
]
