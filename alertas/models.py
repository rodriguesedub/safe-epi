from django.db import models
from django.utils import timezone


class Alerta(models.Model):
    class Tipo(models.TextChoices):
        VALIDADE_EPI = "VALIDADE_EPI", "Validade do EPI"
        VALIDADE_CA = "VALIDADE_CA", "Validade do CA"
        VIDA_UTIL = "VIDA_UTIL", "Fim da vida útil"

    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        RESOLVIDO = "RESOLVIDO", "Resolvido"

    tipo = models.CharField(max_length=14, choices=Tipo.choices)
    unidade = models.ForeignKey(
        "epis.UnidadeEpi", null=True, blank=True, on_delete=models.CASCADE,
        related_name="alertas",
    )
    tipo_epi = models.ForeignKey(
        "epis.TipoEpi", null=True, blank=True, on_delete=models.CASCADE,
        related_name="alertas",
    )
    vence_em = models.DateField()
    dias_antecedencia = models.SmallIntegerField(
        help_text="Faixa do alerta: 30, 15, 7 dias ou 0 (já vencido)."
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTO)
    gerado_em = models.DateTimeField(default=timezone.now)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["vence_em"]
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        indexes = [models.Index(fields=["status", "vence_em"])]

    def __str__(self):
        alvo = self.unidade.codigo if self.unidade_id else self.tipo_epi.nome
        return f"{self.get_tipo_display()}: {alvo} em {self.vence_em:%d/%m/%Y}"

    @property
    def dias_restantes(self):
        return (self.vence_em - timezone.localdate()).days

    @property
    def faixa_label(self):
        if self.dias_antecedencia == 0:
            return "Vencido"
        return f"Até {self.dias_antecedencia} dias"
