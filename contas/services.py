from django.contrib.auth.models import Group, Permission

GRUPOS = {
    "Gestor de SST": {
        "cadastros": ["trabalhador", "atividade", "atividadeepirequisito", "checklistitemmodelo"],
        "epis": ["tipoepi"],
        "_view": [("epis", "unidadeepi"), ("epis", "entregaepi"), ("contas", "usuario")],
    },
    "Almoxarifado": {
        "epis": ["tipoepi", "unidadeepi"],
        "_view": [("cadastros", "trabalhador"), ("epis", "entregaepi")],
    },
}


def configurar_grupos():
    """Permissões do Django Admin por perfil (cadastros via admin, decisão D3)."""
    for nome, regras in GRUPOS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        perms = []
        for app, modelos in regras.items():
            if app == "_view":
                for app_label, modelo in modelos:
                    perms += list(Permission.objects.filter(
                        content_type__app_label=app_label, codename=f"view_{modelo}"))
                continue
            for modelo in modelos:
                perms += list(Permission.objects.filter(
                    content_type__app_label=app,
                    codename__in=[f"{a}_{modelo}" for a in ("add", "change", "view")]))
        grupo.permissions.set(perms)
    return Group.objects.filter(name__in=GRUPOS)


def grupo_do_perfil(perfil):
    return {"GESTOR_SST": "Gestor de SST", "ALMOX": "Almoxarifado"}.get(perfil)
