import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .codigo import gerar_codigo


def hoje():
    return timezone.localdate()


class TipoEpi(models.Model):
    class Categoria(models.TextChoices):
        CABECA = "CABECA", "Proteção da cabeça"
        OLHOS_FACE = "OLHOS_FACE", "Proteção dos olhos e face"
        AUDITIVA = "AUDITIVA", "Proteção auditiva"
        RESPIRATORIA = "RESPIRATORIA", "Proteção respiratória"
        TRONCO = "TRONCO", "Proteção do tronco"
        MAOS = "MAOS", "Proteção das mãos e braços"
        PES = "PES", "Proteção dos pés e pernas"
        QUEDA = "QUEDA", "Proteção contra quedas"
        CORPO = "CORPO", "Proteção do corpo inteiro"

    nome = models.CharField(max_length=120)
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    numero_ca = models.CharField("nº do CA", max_length=12)
    validade_ca = models.DateField("validade do CA")
    vida_util_dias = models.PositiveIntegerField(
        "vida útil (dias)", null=True, blank=True,
        help_text="Contada a partir da entrega. Vazio = sem limite de uso.",
    )
    inspecao_dias = models.PositiveIntegerField(
        "intervalo de inspeção (dias)", null=True, blank=True
    )
    rastreio_individual = models.BooleanField(
        default=True,
        help_text="Desmarque para descartáveis registrados por lote.",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "tipo de EPI"
        verbose_name_plural = "tipos de EPI"

    def __str__(self):
        return self.nome

    def ca_vigente(self, data=None):
        return self.validade_ca >= (data or hoje())


class UnidadeEpi(models.Model):
    class Status(models.TextChoices):
        ESTOQUE = "ESTOQUE", "Em estoque"
        ENTREGUE = "ENTREGUE", "Entregue"
        AVARIADO = "AVARIADO", "Avariado"
        EXTRAVIADO = "EXTRAVIADO", "Extraviado"
        DESCARTADO = "DESCARTADO", "Descartado"

    codigo = models.CharField("código", max_length=20, unique=True, editable=False)
    tipo = models.ForeignKey(TipoEpi, on_delete=models.PROTECT, related_name="unidades")
    serie_lote = models.CharField("série ou lote", max_length=40, blank=True)
    tamanho = models.CharField(max_length=10, blank=True)
    fabricacao = models.DateField("fabricação", null=True, blank=True)
    validade = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ESTOQUE
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "unidade de EPI"
        verbose_name_plural = "unidades de EPI"
        indexes = [models.Index(fields=["validade"])]

    def __str__(self):
        return f"{self.codigo} {self.tipo.nome}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = f"TMP-{uuid.uuid4().hex[:12]}"
            super().save(*args, **kwargs)
            self.codigo = gerar_codigo(self.pk)
            kwargs.pop("force_insert", None)
            super().save(update_fields=["codigo"])
            return
        super().save(*args, **kwargs)

    def vencida(self, data=None):
        return bool(self.validade and self.validade < (data or hoje()))

    @property
    def entrega_ativa(self):
        return self.entregas.filter(devolvido_em__isnull=True).select_related(
            "trabalhador"
        ).first()


class EntregaEpi(models.Model):
    class Motivo(models.TextChoices):
        PRIMEIRA = "PRIMEIRA", "Primeira entrega"
        SUBSTITUICAO = "SUBSTITUICAO", "Substituição"
        TAMANHO = "TAMANHO", "Troca de tamanho"

    unidade = models.ForeignKey(UnidadeEpi, on_delete=models.PROTECT, related_name="entregas")
    trabalhador = models.ForeignKey(
        "cadastros.Trabalhador", on_delete=models.PROTECT, related_name="entregas"
    )
    entregue_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_feitas"
    )
    entregue_em = models.DateTimeField(default=timezone.now)
    devolvido_em = models.DateTimeField(null=True, blank=True)
    motivo = models.CharField(max_length=14, choices=Motivo.choices, default=Motivo.PRIMEIRA)
    observacao = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        ordering = ["-entregue_em"]
        verbose_name = "entrega de EPI"
        verbose_name_plural = "entregas de EPI"
        constraints = [
            models.UniqueConstraint(
                fields=["unidade"],
                condition=models.Q(devolvido_em__isnull=True),
                name="uma_entrega_ativa_por_unidade",
            )
        ]

    def __str__(self):
        return f"{self.unidade.codigo} para {self.trabalhador.nome}"

    @property
    def ativa(self):
        return self.devolvido_em is None

    @property
    def fim_vida_util(self):
        dias = self.unidade.tipo.vida_util_dias
        if not dias:
            return None
        return timezone.localtime(self.entregue_em).date() + timedelta(days=dias)
