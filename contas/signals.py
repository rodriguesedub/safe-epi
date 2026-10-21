from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    from auditoria.services import auditar
    auditar("login", user, usuario=user, request=request, descricao=f"Entrada de {user.username}")
