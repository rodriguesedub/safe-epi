"""Assinatura eletrônica simples com evidências (RF06, RF11, RNF05)."""
import base64
import binascii
import hashlib

from django.core.exceptions import ValidationError
from django.utils import timezone

from auditoria.services import ip_da_requisicao

from .models import Assinatura

PREFIXO_PNG = "data:image/png;base64,"
TAMANHO_MAX = 600 * 1024


def validar_imagem(imagem: str) -> str:
    imagem = (imagem or "").strip()
    if not imagem:
        raise ValidationError("Assine no quadro antes de continuar.")
    if not imagem.startswith(PREFIXO_PNG):
        raise ValidationError("Formato de assinatura inválido.")
    if len(imagem) > TAMANHO_MAX:
        raise ValidationError("Assinatura muito grande. Limpe o quadro e assine de novo.")
    try:
        dados = base64.b64decode(imagem[len(PREFIXO_PNG):], validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("Assinatura corrompida. Limpe o quadro e assine de novo.")
    if not dados.startswith(b"\x89PNG") or len(dados) < 200:
        raise ValidationError("Assinatura vazia. Assine no quadro antes de continuar.")
    return imagem


def criar_assinatura(*, usuario, papel, signatario_nome, imagem, entrega=None,
                     pre_liberacao=None, request=None, validar=True, assinado_em=None):
    if validar:
        imagem = validar_imagem(imagem)
    nome = (signatario_nome or "").strip()
    if not nome:
        raise ValidationError("Informe o nome de quem assinou.")
    assinado_em = assinado_em or timezone.now()
    base = "|".join([imagem, nome, papel, str(usuario.pk), assinado_em.isoformat()])
    return Assinatura.objects.create(
        usuario=usuario,
        papel=papel,
        signatario_nome=nome,
        imagem=imagem,
        hash_sha256=hashlib.sha256(base.encode("utf-8")).hexdigest(),
        entrega=entrega,
        pre_liberacao=pre_liberacao,
        ip=ip_da_requisicao(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""),
        assinado_em=assinado_em,
    )
