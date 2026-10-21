from django.conf import settings
from django.urls import reverse

# Ordem em que as pessoas aparecem no fluxo da demonstração
DEMO_USUARIOS = ["operador", "tecnico", "almox", "gestor", "operador2", "admin"]


def _nav(user):
    principal, mais = [], []
    if user.is_operacional:
        principal += [("Início", "core:inicio", None), ("Solicitar liberação", "liberacoes:nova", None),
                      ("Meus EPIs", "epis:meus", None)]
    if user.is_tecnico:
        principal += [("Conferências", "core:inicio", "n_conferencias"),
                      ("Nova conferência", "liberacoes:nova", None),
                      ("Pré-liberações", "liberacoes:lista", None),
                      ("Colaboradores", "relatorios:busca", None)]
    if user.is_gestor:
        principal += [("Painel", "relatorios:painel", None), ("Estatísticas", "relatorios:estatisticas", None),
                      ("Pré-liberações", "liberacoes:lista", "n_aguardando"),
                      ("Colaboradores", "relatorios:busca", None), ("Alertas", "alertas:painel", None)]
        mais += [("Relatório de conformidade", "relatorios:conformidade"), ("Trilha de auditoria", "auditoria:lista")]
    if user.is_almox:
        if not user.is_gestor:
            principal += [("Início", "core:inicio", None)]
        principal += [("Entregar EPI", "epis:entrega_nova", None), ("Reposições", "reposicao:fila", "n_reposicoes"),
                      ("Unidades", "epis:unidades", None)]
        if not user.is_gestor:
            principal += [("Alertas", "alertas:painel", None)]
        mais += [("Importar planilha", "cadastros:importar")]
    if user.is_staff:
        mais += [("Cadastros", "admin:index")]

    vistos, itens = set(), []
    for rotulo, nome, contador in principal:
        if nome in vistos:
            continue
        vistos.add(nome)
        itens.append({"rotulo": rotulo, "url": reverse(nome), "contador": contador})
    extras = [{"rotulo": r, "url": reverse(n)} for r, n in mais if n not in vistos]
    return itens, extras


def _marcar_atual(nav, path):
    """Marca só o item com o prefixo mais longo (evita dois itens ativos)."""
    candidatos = [i for i in nav if (path == i["url"] if i["url"] == "/" else path.startswith(i["url"]))]
    if candidatos:
        max(candidatos, key=lambda i: len(i["url"]))["atual"] = True
    return nav


def safeepi(request):
    from core.versao import versao_estaticos
    ctx = {"DEMO_MODE": settings.SAFEEPI.get("DEMO_MODE", False), "V": versao_estaticos()}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        nav, extras = _nav(user)
        ctx["nav"] = _marcar_atual(nav, request.path)
        ctx["nav_mais"] = extras
        from liberacoes.models import PreLiberacao
        if user.is_gestor:
            ctx["n_aguardando"] = PreLiberacao.objects.filter(
                status=PreLiberacao.Status.AGUARDANDO_APROVACAO).count()
        if user.is_tecnico:
            ctx["n_conferencias"] = PreLiberacao.objects.filter(
                status=PreLiberacao.Status.EM_CONFERENCIA).count()
        if user.is_almox:
            from reposicao.models import SolicitacaoReposicao
            ctx["n_reposicoes"] = SolicitacaoReposicao.objects.filter(
                status=SolicitacaoReposicao.Status.ABERTA).count()
        for item in ctx["nav"]:
            if item["contador"]:
                item["n"] = ctx.get(item["contador"]) or 0
    if ctx["DEMO_MODE"]:
        from contas.models import Usuario
        usuarios = {u.username: u for u in Usuario.objects.filter(username__in=DEMO_USUARIOS)}
        ctx["demo_usuarios"] = [usuarios[n] for n in DEMO_USUARIOS if n in usuarios]
    return ctx
