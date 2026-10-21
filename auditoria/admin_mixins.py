from .services import auditar


class AuditadoAdmin:
    """Registra na trilha de auditoria toda alteração feita pelo Django Admin."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        campos = list(form.changed_data) if change else []
        auditar(
            "admin.alterado" if change else "admin.criado", obj, request=request,
            descricao=(f"Campos: {', '.join(campos)}" if campos else str(obj))[:400],
            depois={c: str(form.cleaned_data.get(c)) for c in campos} or None,
        )

    def delete_model(self, request, obj):
        auditar("admin.excluido", obj, request=request, descricao=str(obj))
        super().delete_model(request, obj)
