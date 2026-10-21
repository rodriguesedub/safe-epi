from django.urls import path

from . import views

app_name = "liberacoes"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/itens/<int:item_id>/", views.marcar_item, name="marcar_item"),
    path("<int:pk>/itens/<int:item_id>/substituicao/", views.pedir_substituicao,
         name="pedir_substituicao"),
    path("<int:pk>/perguntas/<int:resposta_id>/", views.responder, name="responder"),
    path("<int:pk>/concluir/", views.concluir, name="concluir"),
    path("<int:pk>/decidir/", views.decidir, name="decidir"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/comprovante/", views.comprovante, name="comprovante"),
]
