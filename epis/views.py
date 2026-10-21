from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from auditoria.services import trilha_de
from cadastros.models import Trabalhador
from contas.decorators import perfil_required
from reposicao.models import SolicitacaoReposicao

from .codigo import canonico
from .forms import EntregaForm, unidades_disponiveis
from .models import EntregaEpi, TipoEpi, UnidadeEpi
from .services import entregas_ativas, registrar_entrega, situacao_entrega


@perfil_required("almox", "gestor")
def unidades(request):
    qs = UnidadeEpi.objects.select_related("tipo").order_by("tipo__nome", "codigo")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    tipo = request.GET.get("tipo", "")
    if q:
        qs = qs.filter(Q(codigo__icontains=canonico(q)) | Q(codigo__icontains=q) |
                       Q(serie_lote__icontains=q) | Q(tipo__nome__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if tipo:
        qs = qs.filter(tipo_id=tipo)
    linhas = []
    for u in qs[:300]:
        ativa = u.entregas.filter(devolvido_em__isnull=True).select_related("trabalhador").first()
        linhas.append({"u": u, "entrega": ativa,
                       "situacao": situacao_entrega(ativa) if ativa else _situacao_estoque(u)})
    ctx = {"linhas": linhas, "q": q, "status": status, "tipo": tipo,
           "tipos": TipoEpi.objects.all(), "status_opcoes": UnidadeEpi.Status.choices,
           "total": qs.count()}
    return render(request, "epis/unidades.html", ctx)


def _situacao_estoque(u):
    from .services import avaliar_unidade
    resultado, motivo = avaliar_unidade(u)
    if u.status == UnidadeEpi.Status.DESCARTADO:
        return "neutro", "Descartada"
    return ("ok" if resultado == "OK" else "bloqueio"), motivo


@perfil_required("almox", "gestor")
def unidade_detalhe(request, codigo):
    u = get_object_or_404(UnidadeEpi.objects.select_related("tipo"), codigo=canonico(codigo))
    entregas = u.entregas.select_related("trabalhador", "entregue_por")
    conferencias = u.conferencias.select_related("pre_liberacao__atividade",
                                                  "pre_liberacao__trabalhador")[:20]
    ativa = entregas.filter(devolvido_em__isnull=True).first()
    return render(request, "epis/unidade_detalhe.html", {
        "u": u, "entregas": entregas, "conferencias": conferencias,
        "situacao": situacao_entrega(ativa) if ativa else _situacao_estoque(u),
        "alertas": u.alertas.filter(status="ABERTO"), "trilha": trilha_de(u)[:20],
    })


@perfil_required("almox", "gestor")
def entrega_nova(request):
    solicitacao = None
    inicial = {"motivo": EntregaEpi.Motivo.PRIMEIRA}
    sol_id = request.GET.get("solicitacao") or request.POST.get("solicitacao")
    if sol_id:
        solicitacao = get_object_or_404(SolicitacaoReposicao, pk=sol_id)
        inicial.update(trabalhador=solicitacao.trabalhador, tipo=solicitacao.tipo_epi,
                       signatario_nome=solicitacao.trabalhador.nome,
                       motivo=EntregaEpi.Motivo.SUBSTITUICAO)
    for campo, modelo in (("trabalhador", Trabalhador), ("tipo", TipoEpi)):
        if request.GET.get(campo):
            inicial[campo] = get_object_or_404(modelo, pk=request.GET[campo])
    if inicial.get("trabalhador") and inicial.get("tipo"):
        if entregas_ativas(inicial["trabalhador"], inicial["tipo"]).exists():
            inicial["motivo"] = EntregaEpi.Motivo.SUBSTITUICAO
        inicial.setdefault("signatario_nome", inicial["trabalhador"].nome)

    proximo = request.GET.get("next") or request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()}):
        proximo = ""

    tipo_sel = inicial.get("tipo")
    if request.method == "POST":
        tipo_sel = TipoEpi.objects.filter(pk=request.POST.get("tipo") or 0).first()
        form = EntregaForm(request.POST, tipo=tipo_sel)
        if form.is_valid():
            try:
                entrega = registrar_entrega(
                    unidade=form.cleaned_data["unidade"],
                    trabalhador=form.cleaned_data["trabalhador"],
                    usuario=request.user,
                    assinatura_imagem=form.cleaned_data["assinatura"],
                    signatario_nome=form.cleaned_data["signatario_nome"],
                    motivo=form.cleaned_data["motivo"],
                    solicitacao=solicitacao,
                    observacao=form.cleaned_data["observacao"],
                    request=request,
                )
            except ValidationError as e:
                form.add_error(None, e)
            else:
                messages.success(
                    request,
                    f"Entrega registrada: {entrega.unidade.codigo} para {entrega.trabalhador.nome}.")
                if proximo:
                    return redirect(proximo)
                return redirect("epis:unidade", codigo=entrega.unidade.codigo)
    else:
        form = EntregaForm(initial=inicial, tipo=tipo_sel)
    return render(request, "epis/entrega_form.html",
                  {"form": form, "solicitacao": solicitacao, "next": proximo})


@perfil_required("almox", "gestor")
def opcoes_unidades(request):
    tipo = TipoEpi.objects.filter(pk=request.GET.get("tipo") or 0).first()
    return render(request, "epis/_opcoes_unidades.html", {"unidades": unidades_disponiveis(tipo)})


@perfil_required("operacional", "gestor", "almox")
def meus_epis(request):
    trabalhador = request.user.trabalhador
    if trabalhador is None:
        messages.warning(request, "Seu usuário não está vinculado a um trabalhador.")
        return redirect("core:inicio")
    entregas = [(e, situacao_entrega(e)) for e in entregas_ativas(trabalhador)]
    entregas.sort(key=lambda x: {"bloqueio": 0, "atencao": 1, "ok": 2}[x[1][0]])
    historico = EntregaEpi.objects.filter(trabalhador=trabalhador, devolvido_em__isnull=False
                                          ).select_related("unidade__tipo")[:20]
    solicitacoes = SolicitacaoReposicao.objects.filter(trabalhador=trabalhador
                                                       ).select_related("tipo_epi")[:10]
    return render(request, "epis/meus_epis.html", {
        "trabalhador": trabalhador, "entregas": entregas,
        "historico": historico, "solicitacoes": solicitacoes,
    })


@perfil_required("operacional", "gestor", "almox")
def api_epi(request, codigo):
    """API mínima (D3): consulta de EPI por código, usada pelo leitor de QR na fase 2."""
    u = UnidadeEpi.objects.select_related("tipo").filter(codigo=canonico(codigo)).first()
    if u is None:
        return JsonResponse({"erro": "EPI não encontrado", "codigo": canonico(codigo)}, status=404)
    ativa = u.entregas.filter(devolvido_em__isnull=True).select_related("trabalhador").first()
    situacao, texto = situacao_entrega(ativa) if ativa else _situacao_estoque(u)
    return JsonResponse({
        "codigo": u.codigo, "tipo": u.tipo.nome, "ca": u.tipo.numero_ca,
        "validade_ca": u.tipo.validade_ca.isoformat(),
        "validade": u.validade.isoformat() if u.validade else None,
        "status": u.status, "situacao": situacao, "situacao_texto": texto,
        "trabalhador": ({"matricula": ativa.trabalhador.matricula, "nome": ativa.trabalhador.nome}
                        if ativa else None),
    }, json_dumps_params={"ensure_ascii": False})
