from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def perfil_required(*perfis):
    """Exige login e um dos perfis: 'gestor', 'almox', 'operacional', 'admin'."""

    def decorador(view):
        @wraps(view)
        @login_required
        def _view(request, *args, **kwargs):
            if perfis and not request.user.tem_perfil(*perfis):
                raise PermissionDenied("Seu perfil não tem acesso a esta tela.")
            return view(request, *args, **kwargs)

        return _view

    return decorador
