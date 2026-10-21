from django.contrib import admin

from auditoria.admin_mixins import AuditadoAdmin

from .models import EntregaEpi, TipoEpi, UnidadeEpi


@admin.register(TipoEpi)
class TipoEpiAdmin(AuditadoAdmin, admin.ModelAdmin):
    list_display = ("nome", "categoria", "numero_ca", "validade_ca", "vida_util_dias")
    list_filter = ("categoria",)
    search_fields = ("nome", "numero_ca")


@admin.register(UnidadeEpi)
class UnidadeEpiAdmin(AuditadoAdmin, admin.ModelAdmin):
    list_display = ("codigo", "tipo", "tamanho", "serie_lote", "validade", "status")
    list_filter = ("status", "tipo")
    search_fields = ("codigo", "serie_lote", "tipo__nome")
    readonly_fields = ("codigo",)


@admin.register(EntregaEpi)
class EntregaEpiAdmin(admin.ModelAdmin):
    list_display = ("unidade", "trabalhador", "entregue_em", "devolvido_em", "motivo", "entregue_por")
    list_filter = ("motivo",)
    search_fields = ("unidade__codigo", "trabalhador__nome", "trabalhador__matricula")

    def has_add_permission(self, request):
        return False  # entregas exigem assinatura: use a tela "Entregar EPI"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
