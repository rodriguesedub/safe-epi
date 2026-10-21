from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from contas.decorators import perfil_required

from .models import RegistroAuditoria


@perfil_required("gestor")
def lista(request):
    qs = RegistroAuditoria.objects.select_related("usuario")
    q = request.GET.get("q", "").strip()
    acao = request.GET.get("acao", "")
    if q:
        qs = qs.filter(Q(descricao__icontains=q) | Q(usuario__username__icontains=q) |
                       Q(entidade_id=q))
    if acao:
        qs = qs.filter(acao=acao)
    pagina = Paginator(qs, 50).get_page(request.GET.get("p"))
    acoes = RegistroAuditoria.objects.values_list("acao", flat=True).distinct().order_by("acao")
    return render(request, "auditoria/lista.html",
                  {"pagina": pagina, "q": q, "acao": acao, "acoes": acoes})
