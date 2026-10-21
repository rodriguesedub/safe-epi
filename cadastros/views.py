from django.contrib import messages
from django.shortcuts import render

from contas.decorators import perfil_required

from .importacao import importar_trabalhadores, importar_unidades


@perfil_required("gestor", "almox")
def importar(request):
    resultado = None
    tipo = request.POST.get("tipo", "unidades")
    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            messages.error(request, "Escolha um arquivo CSV.")
        elif arquivo.size > 2 * 1024 * 1024:
            messages.error(request, "Arquivo maior que 2 MB. Divida a planilha.")
        elif tipo == "trabalhadores" and not request.user.is_gestor:
            messages.error(request, "Só o gestor de SST importa trabalhadores.")
        else:
            funcao = importar_trabalhadores if tipo == "trabalhadores" else importar_unidades
            resultado = funcao(arquivo, usuario=request.user, request=request)
            resultado["tipo"] = tipo
    return render(request, "cadastros/importar.html", {"resultado": resultado, "tipo": tipo})
