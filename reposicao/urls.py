from django.urls import path

from . import views

app_name = "reposicao"
urlpatterns = [
    path("", views.fila, name="fila"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/recusar/", views.recusar, name="recusar"),
]
