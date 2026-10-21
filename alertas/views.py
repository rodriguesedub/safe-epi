import csv
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from contas.decorators import perfil_required
from epis.models import UnidadeEpi, hoje

from .models import Alerta
from .services import gerar_alertas


@perfil_required("gestor", "almox")
def painel(request):
    qs = Alerta.objects.filter(status=Alerta.Status.ABERTO).select_related(
        "unidade__tipo", "tipo_epi")
    tipo = request.GET.get("tipo", "")
    faixa = request.GET.get("faixa", "")
    if tipo:
        qs = qs.filter(tipo=tipo)
    if faixa != "":
        qs = qs.filter(dias_antecedencia=faixa)
    linhas = []
    for a in qs:
        trabalhador = None
        if a.unidade_id:
            e = a.unidade.entregas.filter(devolvido_em__isnull=True).select_related("trabalhador").first()
            trabalhador = e.trabalhador if e else None
        linhas.append((a, trabalhador))
    contagem = {f: Alerta.objects.filter(status="ABERTO", dias_antecedencia=f).count()
                for f in (0, 7, 15, 30)}
    return render(request, "alertas/painel.html", {
        "linhas": linhas, "tipo": tipo, "faixa": faixa, "tipos": Alerta.Tipo.choices,
        "contagem": contagem, "compras": _vencimentos_por_tipo(),
    })


def _vencimentos_por_tipo(dias=30):
    """US13: o que vence nos próximos 30 dias, por tipo e tamanho, para planejar compras."""
    limite = hoje() + timedelta(days=dias)
    grupos = defaultdict(int)
    for u in UnidadeEpi.objects.filter(
            status__in=[UnidadeEpi.Status.ESTOQUE, UnidadeEpi.Status.ENTREGUE],
            validade__lte=limite).select_related("tipo"):
        grupos[(u.tipo.nome, u.tamanho or "Único")] += 1
    return sorted(((t, tam, n) for (t, tam), n in grupos.items()), key=lambda x: (-x[2], x[0]))


@perfil_required("gestor", "almox")
def compras_csv(request):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="vencimentos-30-dias.csv"'
    resposta.write("﻿")
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Tipo de EPI", "Tamanho", "Unidades que vencem em 30 dias"])
    for linha in _vencimentos_por_tipo():
        w.writerow(linha)
    return resposta


@require_POST
@perfil_required("gestor", "almox")
def executar(request):
    r = gerar_alertas(usuario=request.user, request=request)
    messages.success(
        request,
        f"Verificação concluída: {r['criados']} novos, {r['resolvidos']} resolvidos, "
        f"{r['abertos']} abertos." + (" Resumo enviado por e-mail (veja o terminal)."
                                       if r["email_enviado"] else ""))
    return redirect("alertas:painel")
