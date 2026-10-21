from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from auditoria.admin_mixins import AuditadoAdmin

from .models import Atividade, AtividadeEpiRequisito, ChecklistItemModelo, Trabalhador


@admin.register(Trabalhador)
class TrabalhadorAdmin(AuditadoAdmin, admin.ModelAdmin):
    list_display = ("matricula", "nome", "funcao", "setor", "ativo")
    list_filter = ("setor", "ativo")
    search_fields = ("matricula", "nome")


class RequisitoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        ativos = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if self.instance.ativa and not ativos:
            raise ValidationError("Atividade ativa precisa de pelo menos um EPI obrigatório.")


class RequisitoInline(admin.TabularInline):
    model = AtividadeEpiRequisito
    formset = RequisitoFormSet
    extra = 1
    autocomplete_fields = ("tipo_epi",)


class PerguntaInline(admin.TabularInline):
    model = ChecklistItemModelo
    extra = 1


@admin.register(Atividade)
class AtividadeAdmin(AuditadoAdmin, admin.ModelAdmin):
    list_display = ("nome", "nr_referencia", "nivel_risco", "exige_aprovacao", "ativa")
    list_filter = ("nivel_risco", "exige_aprovacao", "ativa")
    search_fields = ("nome", "nr_referencia")
    inlines = [RequisitoInline, PerguntaInline]
