from django.utils import timezone

from .models import RegistroAuditoria


def ip_da_requisicao(request):
    if request is None:
        return None
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def auditar(acao, obj=None, *, usuario=None, descricao="", antes=None, depois=None, request=None):
    """Grava uma linha na trilha de auditoria (RF15). Nunca levanta erro de negócio."""
    if usuario is None and request is not None and request.user.is_authenticated:
        usuario = request.user
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    entidade = obj._meta.verbose_name if obj is not None else ""
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        acao=acao,
        entidade=str(entidade),
        entidade_id=str(obj.pk) if obj is not None and obj.pk else "",
        descricao=descricao[:400],
        antes=antes,
        depois=depois,
        ip=ip_da_requisicao(request),
        criado_em=timezone.now(),
    )


def trilha_de(obj):
    return RegistroAuditoria.objects.filter(
        entidade=str(obj._meta.verbose_name), entidade_id=str(obj.pk)
    ).select_related("usuario")
