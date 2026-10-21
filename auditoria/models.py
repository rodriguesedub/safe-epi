from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class RegistroAuditoria(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    acao = models.CharField("ação", max_length=60)
    entidade = models.CharField(max_length=60, blank=True)
    entidade_id = models.CharField(max_length=40, blank=True)
    descricao = models.CharField("descrição", max_length=400, blank=True)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "trilha de auditoria"
        indexes = [models.Index(fields=["entidade", "entidade_id"])]

    def __str__(self):
        return f"{self.criado_em:%d/%m/%Y %H:%M} {self.acao}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("A trilha de auditoria é somente de inclusão.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("A trilha de auditoria não pode ser apagada.")
