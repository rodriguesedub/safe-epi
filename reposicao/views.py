from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from contas.decorators import perfil_required
from epis.models import TipoEpi, UnidadeEpi

from . import services
from .models import SolicitacaoReposicao

R = SolicitacaoReposicao


@perfil_required("almox", "gestor")
def fila(request):
    aba = request.GET.get("aba", "abertas")
    status = {"abertas": R.Status.ABERTA, "atendidas": R.Status.ATENDIDA,
              "recusadas": R.Status.RECUSADA}.get(aba, R.Status.ABERTA)
    qs = R.objects.filter(status=status)
    pedidos = services.fila_ordenada(qs) if status == R.Status.ABERTA else list(
        qs.select_related("trabalhador", "tipo_epi", "entrega__unidade", "atendida_por")
        .order_by("-atendida_em")[:100])
    contagens = {c: R.objects.filter(status=s).count() for c, s in
                 (("abertas", R.Status.ABERTA), ("atendidas", R.Status.ATENDIDA),
                  ("recusadas", R.Status.RECUSADA))}
    return render(request, "reposicao/fila.html", {"pedidos": pedidos, "aba": aba,
                                                   "contagens": contagens})


@perfil_required("operacional", "gestor", "almox")
def nova(request):
    trabalhador = request.user.trabalhador
    if trabalhador is None:
        messages.error(request, "Seu usuário não está vinculado a um trabalhador.")
        return redirect("core:inicio")
    unidade = None
    if request.GET.get("unidade") or request.POST.get("unidade"):
        unidade = get_object_or_404(
            UnidadeEpi, pk=request.GET.get("unidade") or request.POST.get("unidade"),
            entregas__trabalhador=trabalhador, entregas__devolvido_em__isnull=True)
    if request.method == "POST":
        tipo = unidade.tipo if unidade else get_object_or_404(TipoEpi, pk=request.POST.get("tipo_epi") or 0)
        foto = request.FILES.get("foto")
        if foto and foto.size > 5 * 1024 * 1024:
            messages.error(request, "A foto passa de 5 MB. Tire outra com resolução menor.")
        else:
            try:
                services.solicitar_reposicao(
                    trabalhador=trabalhador, tipo_epi=tipo, motivo=request.POST.get("motivo", ""),
                    usuario=request.user, unidade=unidade,
                    observacao=request.POST.get("observacao", ""), foto=foto, request=request)
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages))
            else:
                messages.success(request, f"Pedido de {tipo.nome} enviado ao almoxarifado.")
                return redirect("epis:meus")
    return render(request, "reposicao/nova.html", {
        "unidade": unidade, "tipos": TipoEpi.objects.all(), "motivos": R.Motivo.choices,
    })


@require_POST
@perfil_required("almox", "gestor")
def recusar(request, pk):
    sol = get_object_or_404(R, pk=pk)
    try:
        services.recusar(sol, usuario=request.user, resposta=request.POST.get("resposta", ""),
                         request=request)
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, "; ".join(getattr(e, "messages", [str(e)])))
    else:
        messages.info(request, "Pedido recusado.")
    return redirect("reposicao:fila")
