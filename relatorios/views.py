import csv
from datetime import datetime, time

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from alertas.models import Alerta
from cadastros.models import Atividade, Trabalhador
from contas.decorators import perfil_required
from epis.codigo import canonico
from epis.models import EntregaEpi
from epis.services import entregas_ativas, situacao_entrega
from liberacoes.models import PreLiberacao
from reposicao.models import SolicitacaoReposicao

from .services import indicadores, kpis

S = PreLiberacao.Status


@perfil_required("gestor")
def painel(request):
    k = kpis(30)
    maior_motivo = max([n for _, n in k["motivos"]] or [1])
    return render(request, "relatorios/painel.html", {
        "k": k,
        "indicadores": indicadores(k),
        "motivos": [(m, n, round(100 * n / maior_motivo)) for m, n in k["motivos"]],
        "aguardando": PreLiberacao.objects.filter(status=S.AGUARDANDO_APROVACAO)
        .select_related("atividade", "trabalhador", "conferida_por").order_by("conferida_em")[:6],
        "alertas": Alerta.objects.filter(status=Alerta.Status.ABERTO)
        .select_related("unidade__tipo", "tipo_epi")[:6],
    })


def _data(valor, fim=False):
    try:
        d = datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(datetime.combine(d, time.max if fim else time.min))


def _filtrar(request):
    g = request.GET
    f = {"trabalhador": g.get("trabalhador", "").strip(), "atividade": g.get("atividade", ""),
         "inicio": g.get("inicio", ""), "fim": g.get("fim", ""),
         "epi": g.get("epi", "").strip(), "status": g.get("status", "")}
    pres = PreLiberacao.objects.select_related("atividade", "trabalhador")
    entregas = EntregaEpi.objects.select_related("unidade__tipo", "trabalhador", "entregue_por")
    if f["trabalhador"]:
        cond = Q(trabalhador__nome__icontains=f["trabalhador"]) | Q(trabalhador__matricula__iexact=f["trabalhador"])
        pres, entregas = pres.filter(cond), entregas.filter(cond)
    if f["atividade"]:
        pres = pres.filter(atividade_id=f["atividade"])
        entregas = entregas.filter(unidade__tipo__requisitos__atividade_id=f["atividade"]).distinct()
    if _data(f["inicio"]):
        pres = pres.filter(aberta_em__gte=_data(f["inicio"]))
        entregas = entregas.filter(entregue_em__gte=_data(f["inicio"]))
    if _data(f["fim"], True):
        pres = pres.filter(aberta_em__lte=_data(f["fim"], True))
        entregas = entregas.filter(entregue_em__lte=_data(f["fim"], True))
    if f["epi"]:
        cod = canonico(f["epi"])
        cond_e = (Q(unidade__codigo__icontains=cod) | Q(unidade__tipo__nome__icontains=f["epi"])
                  | Q(unidade__tipo__numero_ca=f["epi"]))
        entregas = entregas.filter(cond_e)
        pres = pres.filter(Q(itens__unidade__codigo__icontains=cod) |
                           Q(itens__tipo_epi__nome__icontains=f["epi"]) |
                           Q(itens__tipo_epi__numero_ca=f["epi"])).distinct()
    if f["status"]:
        pres = pres.filter(status=f["status"])
    return f, pres, entregas


@perfil_required("gestor")
def estatisticas(request):
    from .estatisticas import PERIODOS, estatisticas as calcular
    try:
        dias = int(request.GET.get("dias", 90))
    except ValueError:
        dias = 90
    if dias not in dict(PERIODOS):
        dias = 90
    return render(request, "relatorios/estatisticas.html", {"e": calcular(dias)})


@perfil_required()
def ficha_epi(request, pk):
    """Ficha de controle de EPI do colaborador (registro de fornecimento, NR-6)."""
    t = get_object_or_404(Trabalhador, pk=pk)
    u = request.user
    if not (u.is_conferente or u.is_almox or u.trabalhador_id == t.pk):
        raise PermissionDenied
    entregas = EntregaEpi.objects.filter(trabalhador=t).select_related(
        "unidade__tipo", "entregue_por").prefetch_related("assinaturas").order_by("entregue_em")
    return render(request, "relatorios/ficha_epi.html", {
        "t": t, "entregas": entregas, "gerado_em": timezone.localtime()})


@perfil_required("gestor", "tecnico", "almox")
def busca(request):
    f, pres, entregas = _filtrar(request)
    tem_filtro = any(f.values())
    ctx = {"f": f, "pres": pres[:50], "entregas": entregas[:50],
           "n_pres": pres.count(), "n_entregas": entregas.count(), "tem_filtro": tem_filtro,
           "atividades": Atividade.objects.all(), "status_opcoes": S.choices}
    if request.headers.get("HX-Request"):
        return render(request, "relatorios/_busca_resultados.html", ctx)
    return render(request, "relatorios/busca.html", ctx)


@perfil_required()
def trabalhador(request, pk):
    t = get_object_or_404(Trabalhador, pk=pk)
    u = request.user
    if not (u.is_conferente or u.is_almox or u.trabalhador_id == t.pk):
        raise PermissionDenied
    return render(request, "relatorios/trabalhador.html", {
        "t": t,
        "ativas": [(e, situacao_entrega(e)) for e in entregas_ativas(t)],
        "historico": EntregaEpi.objects.filter(trabalhador=t).select_related(
            "unidade__tipo", "entregue_por")[:50],
        "pres": PreLiberacao.objects.filter(trabalhador=t).select_related("atividade")[:50],
        "solicitacoes": SolicitacaoReposicao.objects.filter(trabalhador=t).select_related("tipo_epi")[:20],
    })


@perfil_required("gestor")
def conformidade(request):
    f, pres, _ = _filtrar(request)
    pres = pres.exclude(status__in=[S.EM_CONFERENCIA, S.AGUARDANDO_APROVACAO]).order_by("aberta_em")
    if request.GET.get("formato") == "csv":
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = 'attachment; filename="relatorio-conformidade.csv"'
        resposta.write("﻿")
        w = csv.writer(resposta, delimiter=";")
        w.writerow(["Número", "Aberta em", "Decidida em", "Minutos", "Atividade", "NR",
                    "Matrícula", "Colaborador", "Local", "PT/OS", "Modo", "Status",
                    "Conferida por", "Decidida por", "Motivo", "Hash SHA-256"])
        for p in pres.select_related("decidida_por", "conferida_por"):
            minutos = round(p.duracao.total_seconds() / 60, 1) if p.duracao else ""
            w.writerow([
                p.numero, timezone.localtime(p.aberta_em).strftime("%d/%m/%Y %H:%M"),
                timezone.localtime(p.decidida_em).strftime("%d/%m/%Y %H:%M") if p.decidida_em else "",
                str(minutos).replace(".", ","), p.atividade.nome, p.atividade.nr_referencia,
                p.trabalhador.matricula, p.trabalhador.nome, p.local, p.numero_pt_os,
                p.modo_label, p.get_status_display(),
                p.conferida_por.username if p.conferida_por else "",
                p.decidida_por.username if p.decidida_por else "", p.motivo, p.hash_sha256,
            ])
        return resposta
    lista = list(pres.select_related("decidida_por", "conferida_por")[:500])
    resumo = {
        "total": len(lista),
        "liberadas": sum(1 for p in lista if p.status == S.LIBERADA),
        "bloqueadas": sum(1 for p in lista if p.status == S.BLOQUEADA),
        "canceladas": sum(1 for p in lista if p.status == S.CANCELADA),
    }
    return render(request, "relatorios/conformidade.html", {
        "f": f, "pres": lista, "resumo": resumo, "atividades": Atividade.objects.all(),
        "gerado_em": timezone.localtime(), "query": request.GET.urlencode(),
    })
