from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from auditoria.admin_mixins import AuditadoAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(AuditadoAdmin, UserAdmin):
    list_display = ("username", "first_name", "last_name", "perfil", "trabalhador", "is_active")
    list_filter = ("perfil", "is_active")
    fieldsets = UserAdmin.fieldsets + (("SAFEEPI", {"fields": ("perfil", "trabalhador")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("SAFEEPI", {"fields": ("perfil", "trabalhador")}),)
    autocomplete_fields = ("trabalhador",)
