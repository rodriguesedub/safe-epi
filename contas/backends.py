from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsuarioOuEmailBackend(ModelBackend):
    """Permite entrar com o nome de usuário ou com o e-mail."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        Usuario = get_user_model()
        usuario = Usuario.objects.filter(
            Q(username__iexact=username.strip()) | Q(email__iexact=username.strip())
        ).order_by("id").first()
        if usuario is None:
            Usuario().set_password(password)  # tempo constante contra enumeração
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
