from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.services import trilha_de
from cadastros.models import Atividade, Trabalhador
from contas.decorators import perfil_required

from . import services
from .models import ChecklistResposta, ConferenciaItem, PreLiberacao

S = PreLiberacao.Status

ABAS = [
    ("aguardando", "Aguardando aprovação", [S.AGUARDANDO_APROVACAO]),
    ("conferencia", "Em conferência", [S.EM_CONFERENCIA]),
    ("liberadas", "Liberadas", [S.LIBERADA]),
    ("bloqueadas", "Bloqueadas", [S.BLOQUEADA]),
    ("todas", "Todas", None),
]


def _erro(request, e):
    texto = "; ".join(e.messages) if isinstance(e, ValidationError) else str(e)
    messages.error(request, texto)


def _obter(request, pk):
    pre = get_object_or_404(
        PreLiberacao.objects.select_related("atividade", "trabalhador", "solicitante", "decidida_por"),
        pk=pk,
    )
    if not services.pode_ver(request.user, pre):
        raise PermissionDenied("Você não tem acesso a esta pré-liberação.")
    return pre


@perfil_required()
def lista(request):
    u = request.user
    qs = PreLiberacao.objects.select_related("atividade", "trabalhador")
    if not (u.is_conferente or u.is_almox):
        qs = qs.filter(trabalhador_id=u.trabalhador_id)
    padrao = "aguardando" if u.is_gestor else ("conferencia" if u.is_tecnico else "todas")
    aba = request.GET.get("aba", padrao)
    contagens = {}
    for chave, _, status in ABAS:
        contagens[chave] = qs.filter(status__in=status).count() if status else qs.count()
    filtro = dict((c, s) for c, _, s in ABAS).get(aba)
    if filtro:
        qs = qs.filter(status__in=filtro)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(trabalhador__nome__icontains=q) | Q(trabalhador__matricula__icontains=q) |
                       Q(atividade__nome__icontains=q) | Q(numero_pt_os__icontains=q))
    return render(request, "liberacoes/lista.html", {
        "pres": qs[:200], "abas": [(c, r, contagens[c]) for c, r, _ in ABAS], "aba": aba, "q": q,
    })


@perfil_required("operacional", "conferente")
def nova(request):
    u = request.user
    atividades = Atividade.objects.filter(ativa=True, requisitos__isnull=False).distinct()
    trabalhadores = Trabalhador.objects.filter(ativo=True) if u.is_conferente else None
    if not u.is_conferente and u.trabalhador is None:
        messages.error(request, "Seu usuário não está vinculado a um colaborador. Fale com o gestor de SST.")
        return redirect("core:inicio")
    dados = request.POST if request.method == "POST" else {}
    if request.method == "POST":
        try:
            atividade = get_object_or_404(atividades, pk=request.POST.get("atividade") or 0)
            if u.is_conferente:
                trabalhador = get_object_or_404(trabalhadores, pk=request.POST.get("trabalhador") or 0)
            else:
                trabalhador = u.trabalhador
            pre = services.abrir_pre_liberacao(
                atividade=atividade, trabalhador=trabalhador, usuario=u,
                local=request.POST.get("local", ""), numero_pt_os=request.POST.get("numero_pt_os", ""),
                request=request,
            )
        except Http404:
            messages.error(request, "Escolha a atividade e o colaborador.")
        except (ValidationError, PermissionDenied) as e:
            _erro(request, e)
        else:
            return redirect("liberacoes:detalhe", pk=pre.pk)
    return render(request, "liberacoes/nova.html", {
        "atividades": atividades.prefetch_related("requisitos__tipo_epi"),
        "trabalhadores": trabalhadores, "dados": dados,
    })


def _sinal_linha(auto, fisico):
    if auto != "OK":
        return "bloqueio"
    return {"CONFORME": "ok", "PENDENTE": "conferir"}.get(fisico, "bloqueio")


def _linhas(pre, itens, respostas):
    """Linhas somente-leitura: do snapshot congelado quando há, senão do estado atual."""
    Auto, Fisico = ConferenciaItem.Auto, ConferenciaItem.Fisico
    if pre.snapshot:
        linhas = [{
            "tipo": i["tipo"], "ca": i["ca"], "unidade": i["unidade"],
            "validade_ca": date.fromisoformat(i["validade_ca"]) if i.get("validade_ca") else None,
            "validade": date.fromisoformat(i["validade"]) if i["validade"] else None,
            "auto": Auto(i["resultado_auto"]).label, "motivo_auto": i["motivo_auto"],
            "fisico": Fisico(i["resultado_fisico"]).label, "observacao": i["observacao"],
            "sinal": _sinal_linha(i["resultado_auto"], i["resultado_fisico"]),
        } for i in pre.snapshot.get("itens", [])]
        checklist = [{"pergunta": r["pergunta"], "bloqueante": r["bloqueante"],
                      "resposta": r["resposta"], "observacao": r["observacao"]}
                     for r in pre.snapshot.get("checklist", [])]
        return linhas, checklist
    linhas = [{
        "tipo": i.tipo_epi.nome, "ca": i.tipo_epi.numero_ca, "validade_ca": i.tipo_epi.validade_ca,
        "unidade": i.unidade.codigo if i.unidade else None,
        "validade": i.unidade.validade if i.unidade else None,
        "auto": i.get_resultado_auto_display(), "motivo_auto": i.motivo_auto,
        "fisico": i.get_resultado_fisico_display(), "observacao": i.observacao,
        "sinal": _sinal_linha(i.resultado_auto, i.resultado_fisico),
    } for i in itens]
    checklist = [{"pergunta": r.item_modelo.texto, "bloqueante": r.item_modelo.bloqueante,
                  "resposta": r.resposta, "observacao": r.observacao} for r in respostas]
    return linhas, checklist


def _contexto_detalhe(request, pre):
    if pre.status == S.EM_CONFERENCIA:
        services.validar_itens(pre)
    itens = list(pre.itens.select_related("tipo_epi", "unidade").order_by("ordem", "id"))
    respostas = list(pre.respostas.select_related("item_modelo"))
    linhas, checklist = _linhas(pre, itens, respostas)
    return {
        "pre": pre,
        "itens": itens,
        "respostas": respostas,
        "linhas": linhas,
        "checklist": checklist,
        "progresso": services.progresso(pre),
        "problemas": services.nao_conformidades(pre),
        "pode_conferir": services.pode_conferir(request.user, pre),
        "pode_decidir": services.pode_decidir(request.user, pre),
        "pode_pedir": services.pode_pedir_substituicao(request.user, pre),
        "do_colaborador": services.e_do_colaborador(request.user, pre),
        "conferiu_esta": request.user.pk == pre.conferida_por_id,
        "pode_substituir": request.user.is_almox and pre.status == S.EM_CONFERENCIA,
        "pode_cancelar": not pre.finalizada and (
            request.user.is_conferente or request.user.pk == pre.solicitante_id),
        "assinaturas": list(pre.assinaturas.select_related("usuario")),
        "trilha": trilha_de(pre),
        "integridade": services.integridade_ok(pre) if pre.finalizada and pre.snapshot else None,
        "opcoes_fisico": [c for c in ConferenciaItem.Fisico.choices if c[0] != "PENDENTE"],
    }


@perfil_required()
def detalhe(request, pk):
    pre = _obter(request, pk)
    return render(request, "liberacoes/detalhe.html", _contexto_detalhe(request, pre))


def _resposta_parcial(request, pre, template, **extra):
    ctx = {
        "pre": pre,
        "progresso": services.progresso(pre),
        "problemas": services.nao_conformidades(pre),
        "pode_conferir": services.pode_conferir(request.user, pre),
        "pode_pedir": services.pode_pedir_substituicao(request.user, pre),
        "pode_substituir": request.user.is_almox and pre.status == S.EM_CONFERENCIA,
        "opcoes_fisico": [c for c in ConferenciaItem.Fisico.choices if c[0] != "PENDENTE"],
        "oob": True,
        **extra,
    }
    return render(request, template, ctx)


@require_POST
@perfil_required("conferente")
def marcar_item(request, pk, item_id):
    pre = _obter(request, pk)
    item = get_object_or_404(ConferenciaItem.objects.select_related("tipo_epi", "unidade"),
                             pk=item_id, pre_liberacao=pre)
    erro = None
    try:
        services.marcar_item(
            item, usuario=request.user,
            resultado_fisico=request.POST.get("resultado", item.resultado_fisico),
            observacao=request.POST.get("observacao", ""),
            foto=request.FILES.get("foto"),
        )
    except (ValidationError, PermissionDenied) as e:
        erro = "; ".join(e.messages) if isinstance(e, ValidationError) else str(e)
    item.refresh_from_db()
    if request.headers.get("HX-Request"):
        return _resposta_parcial(request, pre, "liberacoes/_resposta_item.html", item=item, erro=erro)
    if erro:
        messages.error(request, erro)
    return redirect("liberacoes:detalhe", pk=pre.pk)


@require_POST
@perfil_required("conferente")
def responder(request, pk, resposta_id):
    pre = _obter(request, pk)
    resposta = get_object_or_404(ChecklistResposta.objects.select_related("item_modelo"),
                                 pk=resposta_id, pre_liberacao=pre)
    valor = {"sim": True, "nao": False}.get(request.POST.get("valor"))
    erro = None
    try:
        services.responder_pergunta(resposta, usuario=request.user, valor=valor,
                                    observacao=request.POST.get("observacao"))
    except (ValidationError, PermissionDenied) as e:
        erro = "; ".join(e.messages) if isinstance(e, ValidationError) else str(e)
    resposta.refresh_from_db()
    if request.headers.get("HX-Request"):
        return _resposta_parcial(request, pre, "liberacoes/_resposta_pergunta.html",
                                 r=resposta, erro=erro)
    if erro:
        messages.error(request, erro)
    return redirect("liberacoes:detalhe", pk=pre.pk)


@require_POST
@perfil_required("operacional", "conferente")
def pedir_substituicao(request, pk, item_id):
    from reposicao.services import solicitar_reposicao
    pre = _obter(request, pk)
    item = get_object_or_404(ConferenciaItem, pk=item_id, pre_liberacao=pre)
    if not services.pode_pedir_substituicao(request.user, pre):
        raise PermissionDenied
    motivo = services.motivo_substituicao(item)
    solicitar_reposicao(trabalhador=pre.trabalhador, tipo_epi=item.tipo_epi, motivo=motivo,
                        usuario=request.user, unidade=item.unidade, pre_liberacao=pre,
                        observacao=f"Pedido durante a {pre.numero}", request=request)
    messages.success(request, f"Pedido de substituição de {item.tipo_epi.nome} enviado ao almoxarifado.")
    return redirect("liberacoes:detalhe", pk=pre.pk)


@require_POST
@perfil_required("conferente")
def concluir(request, pk):
    pre = _obter(request, pk)
    try:
        pre = services.concluir_conferencia(
            pre, usuario=request.user,
            assinatura_conferente=request.POST.get("assinatura_conferente", ""),
            assinatura_colaborador=request.POST.get("assinatura_colaborador", ""),
            nome_colaborador=request.POST.get("nome_colaborador", "").strip() or None,
            confirmou_fisico=request.POST.get("confirmou_fisico") == "on",
            observacao=request.POST.get("observacao", "").strip(),
            request=request,
        )
    except (ValidationError, PermissionDenied) as e:
        _erro(request, e)
    else:
        textos = {
            S.LIBERADA: "Atividade liberada. O registro foi gravado com hash e assinatura.",
            S.AGUARDANDO_APROVACAO: "Conferência concluída. Aguardando aprovação do gestor de SST.",
            S.BLOQUEADA: "Atividade bloqueada. Os pedidos de reposição foram enviados ao almoxarifado.",
        }
        messages.success(request, textos.get(pre.status, "Conferência concluída."))
    return redirect("liberacoes:detalhe", pk=pk)


@require_POST
@perfil_required("gestor")
def decidir(request, pk):
    pre = _obter(request, pk)
    liberar = request.POST.get("decisao") == "liberar"
    try:
        pre = services.decidir(
            pre, usuario=request.user, liberar=liberar,
            motivo=request.POST.get("motivo", ""),
            assinatura_imagem=request.POST.get("assinatura", ""),
            signatario_nome=request.POST.get("signatario_nome", ""),
            request=request,
        )
    except (ValidationError, PermissionDenied) as e:
        _erro(request, e)
    else:
        messages.success(request, "Atividade liberada." if liberar else "Atividade bloqueada.")
    return redirect("liberacoes:detalhe", pk=pk)


@require_POST
@perfil_required()
def cancelar(request, pk):
    pre = _obter(request, pk)
    try:
        services.cancelar(pre, usuario=request.user, motivo=request.POST.get("motivo", ""),
                          request=request)
    except (ValidationError, PermissionDenied) as e:
        _erro(request, e)
    else:
        messages.info(request, "Pré-liberação cancelada.")
    return redirect("liberacoes:detalhe", pk=pk)


@perfil_required()
def comprovante(request, pk):
    pre = _obter(request, pk)
    if not pre.finalizada:
        return redirect("liberacoes:detalhe", pk=pk)
    return render(request, "liberacoes/comprovante.html", _contexto_detalhe(request, pre))
