"""Regras de negócio de EPIs: validade e entregas (RF04, RF06, RF09)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from auditoria.services import auditar

from .models import EntregaEpi, UnidadeEpi, hoje


def avaliar_unidade(unidade, entrega=None, data=None):
    """Devolve (resultado, motivo) usando os códigos de ConferenciaItem.Auto."""
    data = data or hoje()
    tipo = unidade.tipo
    if unidade.status == UnidadeEpi.Status.AVARIADO:
        return "AVARIADO", "Unidade registrada como avariada"
    if unidade.status == UnidadeEpi.Status.EXTRAVIADO:
        return "EXTRAVIADO", "Unidade registrada como perdida ou extraviada"
    if unidade.status == UnidadeEpi.Status.DESCARTADO:
        return "AVARIADO", "Unidade descartada"
    if unidade.validade and unidade.validade < data:
        return "VENCIDO", f"Vencido em {unidade.validade:%d/%m/%Y}"
    if entrega is not None and entrega.fim_vida_util and entrega.fim_vida_util < data:
        return "VENCIDO", f"Vida útil encerrada em {entrega.fim_vida_util:%d/%m/%Y}"
    if tipo.validade_ca < data:
        return "CA_VENCIDO", f"CA {tipo.numero_ca} vencido em {tipo.validade_ca:%d/%m/%Y}"
    limites = [d for d in [unidade.validade, entrega.fim_vida_util if entrega else None] if d]
    if limites:
        return "OK", f"Válido até {min(limites):%d/%m/%Y}"
    return "OK", "Sem data de validade"


def entregas_ativas(trabalhador, tipo=None):
    qs = EntregaEpi.objects.filter(trabalhador=trabalhador, devolvido_em__isnull=True)
    if tipo is not None:
        qs = qs.filter(unidade__tipo=tipo)
    return qs.select_related("unidade", "unidade__tipo").order_by("entregue_em", "id")


def _escolher_entrega_a_encerrar(ativas):
    """Na substituição, encerra primeiro a unidade com problema; senão, a mais antiga."""
    for e in ativas:
        resultado, _ = avaliar_unidade(e.unidade, e)
        if resultado != "OK":
            return e, True
    return (ativas[0], False) if ativas else (None, False)


@transaction.atomic
def registrar_entrega(*, unidade, trabalhador, usuario, assinatura_imagem, signatario_nome,
                      motivo=EntregaEpi.Motivo.PRIMEIRA, solicitacao=None, observacao="",
                      request=None, validar_assinatura=True):
    from alertas.services import resolver_alertas_da_unidade
    from liberacoes.assinaturas import criar_assinatura
    from liberacoes.models import Assinatura
    from reposicao.models import SolicitacaoReposicao

    unidade = UnidadeEpi.objects.select_for_update().select_related("tipo").get(pk=unidade.pk)
    if unidade.status != UnidadeEpi.Status.ESTOQUE:
        raise ValidationError(f"{unidade.codigo} não está em estoque ({unidade.get_status_display()}).")
    if unidade.vencida():
        raise ValidationError(f"{unidade.codigo} está vencida. Escolha outra unidade.")
    if not unidade.tipo.ca_vigente():
        raise ValidationError(
            f"O CA {unidade.tipo.numero_ca} de {unidade.tipo.nome} está vencido; "
            "não é permitido entregar este modelo."
        )
    if not trabalhador.ativo:
        raise ValidationError("Trabalhador inativo.")

    encerrada = None
    if motivo in (EntregaEpi.Motivo.SUBSTITUICAO, EntregaEpi.Motivo.TAMANHO):
        ativas = list(entregas_ativas(trabalhador, unidade.tipo))
        encerrada, com_problema = _escolher_entrega_a_encerrar(ativas)
        if encerrada:
            encerrada.devolvido_em = timezone.now()
            encerrada.save(update_fields=["devolvido_em"])
            antiga = encerrada.unidade
            if antiga.status == UnidadeEpi.Status.EXTRAVIADO:
                pass  # perdida continua registrada como extraviada
            elif com_problema:
                antiga.status = UnidadeEpi.Status.DESCARTADO
            else:
                antiga.status = UnidadeEpi.Status.ESTOQUE
            antiga.save(update_fields=["status"])
            resolver_alertas_da_unidade(antiga)

    entrega = EntregaEpi.objects.create(
        unidade=unidade, trabalhador=trabalhador, entregue_por=usuario,
        motivo=motivo, observacao=observacao[:200], entregue_em=timezone.now(),
    )
    unidade.status = UnidadeEpi.Status.ENTREGUE
    unidade.save(update_fields=["status"])
    criar_assinatura(
        usuario=usuario, papel=Assinatura.Papel.TRABALHADOR,
        signatario_nome=signatario_nome, imagem=assinatura_imagem,
        entrega=entrega, request=request, validar=validar_assinatura,
    )

    # Pedidos de reposição deste EPI para este trabalhador ficam atendidos.
    pendentes = SolicitacaoReposicao.objects.filter(
        trabalhador=trabalhador, tipo_epi=unidade.tipo,
        status=SolicitacaoReposicao.Status.ABERTA,
    )
    if solicitacao is not None:
        pendentes = pendentes | SolicitacaoReposicao.objects.filter(pk=solicitacao.pk)
    for s in pendentes.distinct():
        s.status = SolicitacaoReposicao.Status.ATENDIDA
        s.atendida_por = usuario
        s.atendida_em = timezone.now()
        s.entrega = entrega
        s.save(update_fields=["status", "atendida_por", "atendida_em", "entrega"])
        auditar("reposicao.atendida", s, usuario=usuario, request=request,
                descricao=f"Atendida com a entrega de {unidade.codigo}")

    auditar(
        "entrega.registrada", entrega, usuario=usuario, request=request,
        descricao=(
            f"{unidade.codigo} ({unidade.tipo.nome}) para {trabalhador.nome}"
            + (f"; substitui {encerrada.unidade.codigo}" if encerrada else "")
        ),
        depois={"unidade": unidade.codigo, "trabalhador": trabalhador.matricula,
                "motivo": motivo},
    )
    return entrega


def situacao_entrega(entrega, data=None):
    """Resumo para telas: (chave_sinal, texto)."""
    data = data or hoje()
    resultado, motivo = avaliar_unidade(entrega.unidade, entrega, data)
    if resultado != "OK":
        return "bloqueio", motivo
    limites = [d for d in [entrega.unidade.validade, entrega.fim_vida_util] if d]
    if limites and (min(limites) - data).days <= 30:
        return "atencao", f"Vence em {min(limites):%d/%m/%Y}"
    if (entrega.unidade.tipo.validade_ca - data).days <= 30:
        return "atencao", f"CA vence em {entrega.unidade.tipo.validade_ca:%d/%m/%Y}"
    return "ok", motivo
