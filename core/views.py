from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache


@login_required
def inicio(request):
    u = request.user
    if u.is_gestor:
        return redirect("relatorios:painel")
    if u.is_tecnico:
        return _inicio_tecnico(request)
    if u.is_almox:
        return _inicio_almox(request)
    return _inicio_operacional(request)


def _inicio_tecnico(request):
    from liberacoes import services
    from liberacoes.models import PreLiberacao

    S = PreLiberacao.Status
    pendentes = []
    for p in PreLiberacao.objects.filter(status=S.EM_CONFERENCIA).select_related(
            "atividade", "trabalhador", "solicitante").order_by("aberta_em"):
        pendentes.append({"pre": p, "progresso": services.progresso(p),
                          "problemas": sum(1 for i in p.itens.all() if not i.auto_ok)})
    recentes = PreLiberacao.objects.filter(conferida_por=request.user).select_related(
        "atividade", "trabalhador").order_by("-conferida_em")[:6]
    return render(request, "core/inicio_tecnico.html", {"pendentes": pendentes, "recentes": recentes})


def _inicio_operacional(request):
    from epis.services import entregas_ativas, situacao_entrega
    from liberacoes.models import PreLiberacao
    from reposicao.models import SolicitacaoReposicao

    trabalhador = request.user.trabalhador
    ctx = {"trabalhador": trabalhador}
    if trabalhador:
        entregas = [(e, situacao_entrega(e)) for e in entregas_ativas(trabalhador)]
        entregas.sort(key=lambda x: {"bloqueio": 0, "atencao": 1, "ok": 2}[x[1][0]])
        situacoes = [s for _, s in entregas]
        ctx.update(
            entregas=entregas,
            n_ok=sum(1 for s, _ in situacoes if s == "ok"),
            n_atencao=sum(1 for s, _ in situacoes if s == "atencao"),
            n_bloqueio=sum(1 for s, _ in situacoes if s == "bloqueio"),
            em_andamento=PreLiberacao.objects.filter(
                trabalhador=trabalhador,
                status__in=[PreLiberacao.Status.EM_CONFERENCIA,
                            PreLiberacao.Status.AGUARDANDO_APROVACAO],
            ).select_related("atividade"),
            recentes=PreLiberacao.objects.filter(trabalhador=trabalhador).exclude(
                status__in=[PreLiberacao.Status.EM_CONFERENCIA,
                            PreLiberacao.Status.AGUARDANDO_APROVACAO],
            ).select_related("atividade")[:5],
            solicitacoes=SolicitacaoReposicao.objects.filter(
                trabalhador=trabalhador, status=SolicitacaoReposicao.Status.ABERTA,
            ).select_related("tipo_epi"),
        )
    return render(request, "core/inicio_operacional.html", ctx)


def _inicio_almox(request):
    from alertas.models import Alerta
    from epis.models import UnidadeEpi
    from reposicao.models import SolicitacaoReposicao
    from reposicao.services import fila_ordenada

    fila = fila_ordenada(SolicitacaoReposicao.objects.filter(
        status=SolicitacaoReposicao.Status.ABERTA))
    alertas = Alerta.objects.filter(status=Alerta.Status.ABERTO).select_related(
        "unidade__tipo", "tipo_epi")[:8]
    estoque = UnidadeEpi.objects.filter(status=UnidadeEpi.Status.ESTOQUE).count()
    return render(request, "core/inicio_almox.html",
                  {"fila": fila[:6], "n_fila": len(fila), "alertas": alertas, "estoque": estoque})


def manifest(request):
    return JsonResponse({
        "name": "SAFEEPI — Conferência de EPIs",
        "short_name": "SAFEEPI",
        "description": "Pré-liberação segura da atividade: conferência de EPIs no local.",
        "lang": "pt-BR",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#EEF1F4",
        "theme_color": "#134B8A",
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("icons/icon-512-maskable.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }, json_dumps_params={"ensure_ascii": False})


@never_cache
def service_worker(request):
    from core.versao import versao_estaticos
    v = versao_estaticos()
    js = render_to_string("core/sw.js", {
        "versao": v,
        "arquivos": [
            "/offline/",
            *(f"{static(a)}?v={v}" for a in ("css/app.css", "js/htmx.min.js", "js/app.js", "js/assinatura.js")),
            static("icons/icon-192.png"),
            static("fonts/barlow-latin-400-normal.woff2"),
            static("fonts/barlow-latin-500-normal.woff2"),
            static("fonts/barlow-latin-600-normal.woff2"),
            static("fonts/barlow-latin-700-normal.woff2"),
        ],
    })
    resposta = HttpResponse(js, content_type="application/javascript")
    resposta["Service-Worker-Allowed"] = "/"
    return resposta


def offline(request):
    return render(request, "core/offline.html")


@require_POST
def demo_iniciar(request):
    """Volta os dados ao estado inicial, entra como o colaborador João e inicia o tour."""
    if not settings.SAFEEPI.get("DEMO_MODE"):
        raise Http404
    modo = request.POST.get("modo") if request.POST.get("modo") in ("guiado", "auto") else "guiado"
    extras = ""
    try:
        vel = float(request.POST.get("vel", "1"))
    except ValueError:
        vel = 1.0
    if vel != 1.0 and 0.5 <= vel <= 3:
        extras += f"&vel={vel:g}"
    if request.POST.get("contagem") == "0":
        extras += "&contagem=0"

    from contas.models import Usuario
    if not Usuario.objects.filter(username="operador").exists():
        call_command("seed_demo", reset=True, verbosity=0)
    elif settings.DEBUG:
        call_command("seed_demo", reset=True, verbosity=0)
    else:
        # Em produção com dados já carregados, limpa apenas pendências recentes do João
        # para que o tour possa recomeçar instantaneamente sem timeout de HTTP
        try:
            from cadastros.models import Trabalhador
            from liberacoes.models import PreLiberacao
            trab = Trabalhador.objects.filter(matricula="T1001").first()
            if trab:
                PreLiberacao.objects.filter(
                    trabalhador=trab,
                    status__in=[PreLiberacao.Status.EM_CONFERENCIA, PreLiberacao.Status.AGUARDANDO_APROVACAO]
                ).delete()
        except Exception:
            pass

    login(request, Usuario.objects.get(username="operador"),
          backend="contas.backends.UsuarioOuEmailBackend")
    return redirect(f"/?tour={modo}{extras}")
