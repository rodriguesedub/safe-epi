from django.contrib import admin

from .models import SolicitacaoReposicao


@admin.register(SolicitacaoReposicao)
class SolicitacaoReposicaoAdmin(admin.ModelAdmin):
    list_display = ("trabalhador", "tipo_epi", "motivo", "status", "criada_em", "atendida_em")
    list_filter = ("status", "motivo")
