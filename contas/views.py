from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Usuario


class Entrar(LoginView):
    template_name = "contas/login.html"
    redirect_authenticated_user = True


@require_POST
def sair(request):
    logout(request)
    return redirect("contas:login")


@require_POST
def demo_entrar(request, username):
    """Troca rápida de usuário para apresentações (só com SAFEEPI_DEMO ligado)."""
    if not settings.SAFEEPI.get("DEMO_MODE"):
        raise Http404
    usuario = get_object_or_404(Usuario, username=username, is_active=True)
    login(request, usuario, backend="contas.backends.UsuarioOuEmailBackend")
    messages.info(request, f"Você entrou como {usuario.nome_exibicao} ({usuario.get_perfil_display()}).")
    destino = request.POST.get("next") or "core:inicio"
    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)
    return redirect("core:inicio")
