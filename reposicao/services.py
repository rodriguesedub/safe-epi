"""Solicitações de reposição (RF16) e registro de avaria (RF19)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from auditoria.services import auditar
from epis.models import UnidadeEpi

from .models import SolicitacaoReposicao

R = SolicitacaoReposicao


@transaction.atomic
def solicitar_reposicao(*, trabalhador, tipo_epi, motivo, usuario, unidade=None,
                        pre_liberacao=None, observacao="", foto=None, request=None):
    if motivo not in R.Motivo.values:
        raise ValidationError("Motivo inválido.")
    existente = R.objects.filter(
        trabalhador=trabalhador, tipo_epi=tipo_epi, status=R.Status.ABERTA
    ).first()
    if existente:
        campos = []
        if pre_liberacao is not None and existente.pre_liberacao_id is None:
            existente.pre_liberacao = pre_liberacao
            campos.append("pre_liberacao")
        if foto is not None and not existente.foto:
            existente.foto = foto
            campos.append("foto")
        if campos:
            existente.save(update_fields=campos)
        sol = existente
    else:
        sol = R.objects.create(
            trabalhador=trabalhador, tipo_epi=tipo_epi, motivo=motivo,
            unidade_substituida=unidade, pre_liberacao=pre_liberacao,
            observacao=(observacao or "")[:300], foto=foto, solicitada_por=usuario,
            criada_em=timezone.now(),
        )
        auditar("reposicao.solicitada", sol, usuario=usuario, request=request,
                descricao=f"{tipo_epi.nome} para {trabalhador.nome}: {sol.get_motivo_display()}")

    # Avaria ou perda informada tira a unidade de uso (F13)
    novo_status = {R.Motivo.DANIFICADO: UnidadeEpi.Status.AVARIADO,
                   R.Motivo.PERDA: UnidadeEpi.Status.EXTRAVIADO}.get(motivo)
    if novo_status and unidade is not None and unidade.status == UnidadeEpi.Status.ENTREGUE:
        unidade.status = novo_status
        unidade.save(update_fields=["status"])
        acao = "unidade.avariada" if novo_status == UnidadeEpi.Status.AVARIADO else "unidade.extraviada"
        auditar(acao, unidade, usuario=usuario, request=request,
                descricao=f"{sol.get_motivo_display()} informada: {(observacao or '')[:200]}")
    return sol


def recusar(sol, *, usuario, resposta, request=None):
    if sol.status != R.Status.ABERTA:
        raise ValidationError("Só pedidos abertos podem ser recusados.")
    if len((resposta or "").strip()) < 5:
        raise ValidationError("Explique o motivo da recusa.")
    sol.status = R.Status.RECUSADA
    sol.resposta = resposta.strip()[:300]
    sol.atendida_por = usuario
    sol.atendida_em = timezone.now()
    sol.save(update_fields=["status", "resposta", "atendida_por", "atendida_em"])
    auditar("reposicao.recusada", sol, usuario=usuario, request=request, descricao=sol.resposta)
    return sol


def fila_ordenada(qs):
    """Prioridade: trabalhador esperando no local (conferência aberta), depois pedidos
    que bloquearam uma atividade, depois os demais; dentro de cada grupo, o mais antigo."""
    itens = list(qs.select_related("trabalhador", "tipo_epi", "unidade_substituida",
                                   "pre_liberacao", "solicitada_por"))

    def prioridade(s):
        if s.aguardando_no_local:
            return 0
        return 1 if s.bloqueando else 2

    return sorted(itens, key=lambda s: (prioridade(s), s.criada_em))
