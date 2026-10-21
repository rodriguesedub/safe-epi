from django.contrib import admin

from .models import Assinatura, PreLiberacao


class SomenteLeitura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PreLiberacao)
class PreLiberacaoAdmin(SomenteLeitura):
    list_display = ("numero", "atividade", "trabalhador", "status", "aberta_em", "decidida_em")
    list_filter = ("status", "atividade")
    search_fields = ("trabalhador__nome", "trabalhador__matricula", "numero_pt_os")


@admin.register(Assinatura)
class AssinaturaAdmin(SomenteLeitura):
    list_display = ("signatario_nome", "papel", "usuario", "assinado_em", "hash_sha256")
