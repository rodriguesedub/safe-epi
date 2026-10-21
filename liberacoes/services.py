"""Fluxo de pré-liberação (seção 7 da especificação).

O sistema sinaliza; uma pessoa confere fisicamente e decide (RNF06).
Toda regra fica aqui, fora das views (RNF12).
"""
import hashlib
import json
from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from auditoria.services import auditar
from epis.models import UnidadeEpi, hoje
from epis.services import avaliar_unidade, entregas_ativas

from .assinaturas import criar_assinatura
from .models import Assinatura, ChecklistResposta, ConferenciaItem, PreLiberacao

S = PreLiberacao.Status


# ---------------------------------------------------------------- permissões

def e_do_colaborador(usuario, pre):
    return usuario.trabalhador_id is not None and usuario.trabalhador_id == pre.trabalhador_id


def pode_ver(usuario, pre):
    return usuario.is_conferente or usuario.is_almox or e_do_colaborador(usuario, pre)


def pode_conferir(usuario, pre):
    """Segregação de funções: quem usa o EPI não certifica o próprio EPI."""
    return (pre.status == S.EM_CONFERENCIA and usuario.is_conferente
            and not e_do_colaborador(usuario, pre))


def pode_decidir(usuario, pre):
    """A aprovação é de um gestor de SST diferente de quem fez a conferência."""
    return (pre.status == S.AGUARDANDO_APROVACAO and usuario.is_gestor
            and usuario.pk != pre.conferida_por_id and not e_do_colaborador(usuario, pre))


def pode_pedir_substituicao(usuario, pre):
    return pre.status == S.EM_CONFERENCIA and (
        pode_conferir(usuario, pre) or e_do_colaborador(usuario, pre))


# ---------------------------------------------------------------- abertura

@transaction.atomic
def abrir_pre_liberacao(*, atividade, trabalhador, usuario, local, numero_pt_os="", request=None):
    if not atividade.ativa:
        raise ValidationError("Esta atividade está inativa.")
    requisitos = list(atividade.requisitos.select_related("tipo_epi"))
    if not requisitos:
        raise ValidationError("A atividade não tem EPIs obrigatórios cadastrados.")
    if not trabalhador.ativo:
        raise ValidationError("Trabalhador inativo.")
    if not usuario.is_conferente and usuario.trabalhador_id != trabalhador.pk:
        raise PermissionDenied("Você só pode solicitar liberação para você mesmo.")
    if not (local or "").strip():
        raise ValidationError("Informe o local da atividade.")

    pre = PreLiberacao.objects.create(
        atividade=atividade, trabalhador=trabalhador, solicitante=usuario,
        local=local.strip(), numero_pt_os=(numero_pt_os or "").strip(),
        exige_aprovacao=atividade.exige_aprovacao, aberta_em=timezone.now(),
    )
    ordem = 0
    for req in requisitos:
        for _ in range(req.quantidade):
            ConferenciaItem.objects.create(pre_liberacao=pre, tipo_epi=req.tipo_epi, ordem=ordem)
            ordem += 1
    for pergunta in atividade.perguntas.all():
        ChecklistResposta.objects.create(pre_liberacao=pre, item_modelo=pergunta)
    validar_itens(pre)
    auditar("pre_liberacao.aberta", pre, usuario=usuario, request=request,
            descricao=f"{atividade.nome} para {trabalhador.nome} em {pre.local}")
    return pre


# ---------------------------------------------------------------- validação automática

def validar_itens(pre, data=None):
    """Vincula cada item a um EPI entregue e avalia validade, CA e avaria (RF08, RF09).

    Pode ser chamada várias vezes enquanto a conferência está aberta: se o EPI
    vinculado mudar (por exemplo, após uma substituição no local), a marcação
    física daquele item volta para 'A conferir'.
    """
    if pre.status != S.EM_CONFERENCIA:
        return
    data = data or hoje()
    por_tipo = defaultdict(list)
    for item in pre.itens.select_related("tipo_epi", "unidade").order_by("ordem", "id"):
        por_tipo[item.tipo_epi_id].append(item)

    for itens in por_tipo.values():
        ativas = list(entregas_ativas(pre.trabalhador, itens[0].tipo_epi))
        # unidades em ordem: as válidas primeiro, para não marcar falso bloqueio
        ativas.sort(key=lambda e: avaliar_unidade(e.unidade, e, data)[0] != "OK")
        for i, item in enumerate(itens):
            entrega = ativas[i] if i < len(ativas) else None
            if entrega is None:
                novo_unidade, resultado, motivo = None, "NAO_ENTREGUE", (
                    "Nenhuma entrega ativa deste EPI para o trabalhador"
                )
            else:
                novo_unidade = entrega.unidade
                resultado, motivo = avaliar_unidade(entrega.unidade, entrega, data)
            mudou_unidade = item.unidade_id != (novo_unidade.pk if novo_unidade else None)
            if mudou_unidade or item.resultado_auto != resultado or item.motivo_auto != motivo:
                item.unidade = novo_unidade
                item.resultado_auto = resultado
                item.motivo_auto = motivo
                campos = ["unidade", "resultado_auto", "motivo_auto"]
                if mudou_unidade and not item.pendente:
                    item.resultado_fisico = ConferenciaItem.Fisico.PENDENTE
                    item.conferido_em = None
                    item.foto = None
                    campos += ["resultado_fisico", "conferido_em", "foto"]
                item.save(update_fields=campos)


# ---------------------------------------------------------------- conferência

def _exigir_conferencia(usuario, pre):
    if pre.status != S.EM_CONFERENCIA:
        raise ValidationError("Esta pré-liberação não está mais em conferência.")
    if e_do_colaborador(usuario, pre):
        raise PermissionDenied(
            "A conferência dos seus EPIs é feita pelo técnico de segurança, não por você.")
    if not pode_conferir(usuario, pre):
        raise PermissionDenied("Só o técnico de segurança ou o gestor de SST faz a conferência.")


def marcar_item(item, *, usuario, resultado_fisico, observacao="", foto=None):
    pre = item.pre_liberacao
    _exigir_conferencia(usuario, pre)
    if resultado_fisico not in ConferenciaItem.Fisico.values:
        raise ValidationError("Resultado inválido.")
    item.resultado_fisico = resultado_fisico
    item.observacao = (observacao or "")[:300]
    if foto is not None:
        item.foto = foto
    item.conferido_em = None if resultado_fisico == ConferenciaItem.Fisico.PENDENTE else timezone.now()
    item.save()
    return item


def responder_pergunta(resposta, *, usuario, valor, observacao=None):
    _exigir_conferencia(usuario, resposta.pre_liberacao)
    resposta.resposta = valor
    if observacao is not None:
        resposta.observacao = observacao[:300]
    resposta.save()
    return resposta


def progresso(pre):
    itens = list(pre.itens.all())
    respostas = list(pre.respostas.select_related("item_modelo"))
    total = len(itens) + len(respostas)
    feitos = sum(1 for i in itens if not i.pendente) + sum(1 for r in respostas if r.resposta is not None)
    return {"total": total, "feitos": feitos, "restantes": total - feitos,
            "pct": round(100 * feitos / total) if total else 100, "completo": feitos == total}


def nao_conformidades(pre):
    """Lista legível do que impede a liberação."""
    problemas = []
    for item in pre.itens.select_related("tipo_epi", "unidade"):
        if not item.auto_ok:
            problemas.append(f"{item.tipo_epi.nome}: {item.motivo_auto}")
        elif item.resultado_fisico not in (ConferenciaItem.Fisico.CONFORME, ConferenciaItem.Fisico.PENDENTE):
            problemas.append(f"{item.tipo_epi.nome}: {item.get_resultado_fisico_display().lower()} na conferência física")
    for r in pre.respostas.select_related("item_modelo"):
        if r.nao_conforme:
            problemas.append(f"Checklist: \"{r.item_modelo.texto}\" respondido com Não")
    return problemas


_MOTIVO_REPOSICAO = {
    "VENCIDO": "VENCIDO", "CA_VENCIDO": "VENCIDO", "AVARIADO": "DANIFICADO",
    "EXTRAVIADO": "PERDA", "NAO_ENTREGUE": "NAO_ENTREGUE",
}
# EPI "ausente" na conferência bloqueia, mas não vira perda automaticamente:
# o colaborador pode só ter esquecido. A perda é declarada pedindo a substituição.
_MOTIVO_FISICO = {"DANIFICADO": "DANIFICADO", "VENCIDO": "VENCIDO"}


def motivo_substituicao(item):
    """Motivo do pedido feito à mão durante a conferência."""
    return (_MOTIVO_REPOSICAO.get(item.resultado_auto)
            or {"AUSENTE": "PERDA"}.get(item.resultado_fisico)
            or _MOTIVO_FISICO.get(item.resultado_fisico, "DANIFICADO"))


@transaction.atomic
def concluir_conferencia(pre, *, usuario, assinatura_conferente, assinatura_colaborador,
                         nome_colaborador=None, confirmou_fisico, observacao="", request=None,
                         validar_assinatura=True):
    """O conferente conclui; colaborador e conferente assinam no mesmo aparelho."""
    pre = PreLiberacao.objects.select_for_update().get(pk=pre.pk)
    _exigir_conferencia(usuario, pre)
    validar_itens(pre)
    if not progresso(pre)["completo"]:
        raise ValidationError("Confira todos os itens e responda todas as perguntas antes de concluir.")
    if not confirmou_fisico:
        raise ValidationError("Confirme que a conferência física foi feita.")

    agora = timezone.now()
    criar_assinatura(
        usuario=usuario, papel=Assinatura.Papel.CONFERENTE,
        signatario_nome=usuario.nome_exibicao, imagem=assinatura_conferente,
        pre_liberacao=pre, request=request, validar=validar_assinatura,
    )
    criar_assinatura(
        usuario=usuario, papel=Assinatura.Papel.TRABALHADOR,
        signatario_nome=(nome_colaborador or pre.trabalhador.nome), imagem=assinatura_colaborador,
        pre_liberacao=pre, request=request, validar=validar_assinatura,
    )
    pre.conferida_em = agora
    pre.conferida_por = usuario
    pre.conferencia_fisica_confirmada = True

    # EPI marcado como danificado sai de uso (F13)
    for item in pre.itens.filter(resultado_fisico=ConferenciaItem.Fisico.DANIFICADO, unidade__isnull=False):
        unidade = item.unidade
        if unidade.status != UnidadeEpi.Status.AVARIADO:
            unidade.status = UnidadeEpi.Status.AVARIADO
            unidade.save(update_fields=["status"])
            auditar("unidade.avariada", unidade, usuario=usuario, request=request,
                    descricao=f"Marcada como danificada na conferência {pre.numero}")

    problemas = nao_conformidades(pre)
    if problemas:
        motivo = "Bloqueada na conferência. " + "; ".join(problemas)
        if observacao:
            motivo += f". Observação: {observacao}"
        _abrir_reposicoes(pre, usuario, request)
        _decidir(pre, S.BLOQUEADA, usuario, motivo, request)
    elif pre.exige_aprovacao:
        pre.status = S.AGUARDANDO_APROVACAO
        pre.save()
        auditar("pre_liberacao.conferida", pre, usuario=usuario, request=request,
                descricao=f"Conferência 100% conforme por {usuario.nome_exibicao}; "
                          "aguardando aprovação do gestor de SST")
    else:
        _decidir(pre, S.LIBERADA, usuario,
                 "Liberada em modo registro: conferência 100% conforme." +
                 (f" Observação: {observacao}" if observacao else ""), request)
    return pre


def _abrir_reposicoes(pre, usuario, request):
    from reposicao.services import solicitar_reposicao
    for item in pre.itens.select_related("tipo_epi", "unidade"):
        if not item.auto_ok:
            motivo = _MOTIVO_REPOSICAO.get(item.resultado_auto, "VENCIDO")
        elif item.resultado_fisico in _MOTIVO_FISICO:
            motivo = _MOTIVO_FISICO[item.resultado_fisico]
        else:
            continue
        solicitar_reposicao(
            trabalhador=pre.trabalhador, tipo_epi=item.tipo_epi, motivo=motivo,
            usuario=usuario, unidade=item.unidade, pre_liberacao=pre,
            observacao=f"Aberta automaticamente pela {pre.numero}", request=request,
        )


# ---------------------------------------------------------------- decisão

@transaction.atomic
def decidir(pre, *, usuario, liberar, motivo, assinatura_imagem, signatario_nome,
            request=None, validar_assinatura=True):
    pre = PreLiberacao.objects.select_for_update().get(pk=pre.pk)
    if not pode_decidir(usuario, pre):
        if pre.status == S.AGUARDANDO_APROVACAO and usuario.pk == pre.conferida_por_id:
            raise PermissionDenied(
                "Quem fez a conferência não aprova a mesma pré-liberação. "
                "A aprovação é de outro gestor de SST.")
        raise PermissionDenied("Só o gestor de SST decide pré-liberações aguardando aprovação.")
    motivo = (motivo or "").strip()
    if liberar:
        # Reavalia: algo pode ter vencido entre a conferência e a aprovação.
        for item in pre.itens.select_related("unidade", "tipo_epi"):
            if item.unidade is None:
                raise ValidationError(f"{item.tipo_epi.nome} sem EPI vinculado.")
            entrega = item.unidade.entregas.filter(
                trabalhador=pre.trabalhador, devolvido_em__isnull=True).first()
            resultado, texto = avaliar_unidade(item.unidade, entrega)
            if resultado != "OK" or entrega is None:
                raise ValidationError(
                    f"{item.tipo_epi.nome} deixou de estar conforme ({texto or 'entrega encerrada'}). "
                    "Bloqueie e abra uma nova pré-liberação."
                )
    elif len(motivo) < 10:
        raise ValidationError("Explique o motivo do bloqueio (mínimo de 10 caracteres).")

    criar_assinatura(
        usuario=usuario, papel=Assinatura.Papel.RESPONSAVEL,
        signatario_nome=signatario_nome, imagem=assinatura_imagem,
        pre_liberacao=pre, request=request, validar=validar_assinatura,
    )
    if not liberar:
        _abrir_reposicoes(pre, usuario, request)
    _decidir(pre, S.LIBERADA if liberar else S.BLOQUEADA, usuario,
             motivo or "Aprovada pelo gestor de SST.", request)
    return pre


@transaction.atomic
def cancelar(pre, *, usuario, motivo, request=None):
    if pre.finalizada:
        raise ValidationError("Pré-liberação já finalizada.")
    if not (usuario.is_conferente or usuario.pk == pre.solicitante_id):
        raise PermissionDenied("Só quem abriu ou a equipe de SST pode cancelar.")
    if len((motivo or "").strip()) < 5:
        raise ValidationError("Informe o motivo do cancelamento.")
    pre.status = S.CANCELADA
    pre.motivo = motivo.strip()
    pre.decidida_em = timezone.now()
    pre.decidida_por = usuario
    _salvar_finalizacao(pre)
    auditar("pre_liberacao.cancelada", pre, usuario=usuario, request=request, descricao=pre.motivo)
    return pre


def _salvar_finalizacao(pre):
    """Única gravação permitida de um registro final; depois disso ele é imutável."""
    pre._permitir_finalizacao = True
    try:
        pre.save()
    finally:
        del pre._permitir_finalizacao


def _decidir(pre, status, usuario, motivo, request=None):
    pre.status = status
    pre.decidida_em = timezone.now()
    pre.decidida_por = usuario
    pre.motivo = motivo[:2000]
    pre.snapshot = montar_snapshot(pre)
    pre.hash_sha256 = calcular_hash(pre.snapshot)
    _salvar_finalizacao(pre)
    auditar(
        "pre_liberacao.liberada" if status == S.LIBERADA else "pre_liberacao.bloqueada",
        pre, usuario=usuario, request=request, descricao=motivo[:400],
        depois={"status": status, "hash": pre.hash_sha256},
    )


# ---------------------------------------------------------------- registro imutável

def montar_snapshot(pre):
    """Congela o estado no momento da decisão (validades, CA, respostas, assinaturas)."""
    def d(x):
        return x.isoformat() if x else None

    return {
        "numero": pre.numero,
        "status": pre.status,
        "modo": "aprovacao" if pre.exige_aprovacao else "registro",
        "atividade": {"id": pre.atividade_id, "nome": pre.atividade.nome,
                      "nr": pre.atividade.nr_referencia},
        "trabalhador": {"matricula": pre.trabalhador.matricula, "nome": pre.trabalhador.nome},
        "local": pre.local,
        "numero_pt_os": pre.numero_pt_os,
        "aberta_em": d(pre.aberta_em),
        "conferida_em": d(pre.conferida_em),
        "conferida_por": pre.conferida_por.username if pre.conferida_por else None,
        "decidida_em": d(pre.decidida_em),
        "decidida_por": pre.decidida_por.username if pre.decidida_por else None,
        "conferencia_fisica_confirmada": pre.conferencia_fisica_confirmada,
        "motivo": pre.motivo,
        "itens": [
            {
                "tipo": i.tipo_epi.nome,
                "ca": i.tipo_epi.numero_ca,
                "validade_ca": d(i.tipo_epi.validade_ca),
                "unidade": i.unidade.codigo if i.unidade else None,
                "validade": d(i.unidade.validade) if i.unidade else None,
                "resultado_auto": i.resultado_auto,
                "motivo_auto": i.motivo_auto,
                "resultado_fisico": i.resultado_fisico,
                "observacao": i.observacao,
            }
            for i in pre.itens.select_related("tipo_epi", "unidade").order_by("ordem", "id")
        ],
        "checklist": [
            {"pergunta": r.item_modelo.texto, "bloqueante": r.item_modelo.bloqueante,
             "resposta": r.resposta, "observacao": r.observacao}
            for r in pre.respostas.select_related("item_modelo")
        ],
        "assinaturas": [
            {"papel": a.papel, "nome": a.signatario_nome, "usuario": a.usuario.username,
             "hash": a.hash_sha256, "assinado_em": d(a.assinado_em)}
            for a in pre.assinaturas.select_related("usuario")
        ],
    }


def calcular_hash(snapshot):
    texto = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def integridade_ok(pre):
    return bool(pre.snapshot) and calcular_hash(pre.snapshot) == pre.hash_sha256
