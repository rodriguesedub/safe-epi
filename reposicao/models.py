from django.conf import settings
from django.db import models
from django.utils import timezone


class SolicitacaoReposicao(models.Model):
    class Motivo(models.TextChoices):
        VENCIDO = "VENCIDO", "Vencido"
        DANIFICADO = "DANIFICADO", "Danificado"
        PERDA = "PERDA", "Perda ou extravio"
        TAMANHO = "TAMANHO", "Tamanho inadequado"
        NAO_ENTREGUE = "NAO_ENTREGUE", "Nunca foi entregue"

    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        ATENDIDA = "ATENDIDA", "Atendida"
        RECUSADA = "RECUSADA", "Recusada"

    trabalhador = models.ForeignKey(
        "cadastros.Trabalhador", on_delete=models.PROTECT, related_name="solicitacoes"
    )
    tipo_epi = models.ForeignKey(
        "epis.TipoEpi", on_delete=models.PROTECT, related_name="solicitacoes",
        verbose_name="tipo de EPI",
    )
    unidade_substituida = models.ForeignKey(
        "epis.UnidadeEpi", null=True, blank=True, on_delete=models.PROTECT,
        related_name="solicitacoes",
    )
    pre_liberacao = models.ForeignKey(
        "liberacoes.PreLiberacao", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="solicitacoes",
        help_text="Pré-liberação que originou o pedido (fica no topo da fila).",
    )
    motivo = models.CharField(max_length=14, choices=Motivo.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    observacao = models.CharField("observação", max_length=300, blank=True)
    foto = models.FileField(upload_to="avarias/%Y/%m/", null=True, blank=True)
    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes_feitas"
    )
    atendida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="solicitacoes_atendidas",
    )
    entrega = models.ForeignKey(
        "epis.EntregaEpi", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="solicitacoes",
    )
    resposta = models.CharField(max_length=300, blank=True)
    criada_em = models.DateTimeField(default=timezone.now)
    atendida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        verbose_name = "solicitação de reposição"
        verbose_name_plural = "solicitações de reposição"

    def __str__(self):
        return f"{self.tipo_epi.nome} para {self.trabalhador.nome} ({self.get_status_display()})"

    @property
    def bloqueando(self):
        return bool(
            self.pre_liberacao_id
            and self.status == self.Status.ABERTA
            and self.pre_liberacao.status != "LIBERADA"
        )

    @property
    def aguardando_no_local(self):
        """Pré-liberação ainda aberta: o trabalhador está esperando o EPI para começar."""
        return self.bloqueando and self.pre_liberacao.status in ("EM_CONFERENCIA", "AGUARDANDO_APROVACAO")
