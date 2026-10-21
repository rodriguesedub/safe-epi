from django.contrib import admin

from .models import Alerta


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("tipo", "unidade", "tipo_epi", "vence_em", "dias_antecedencia", "status")
    list_filter = ("tipo", "status", "dias_antecedencia")
