from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PreLiberacao(models.Model):
    class Status(models.TextChoices):
        EM_CONFERENCIA = "EM_CONFERENCIA", "Em conferência"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        LIBERADA = "LIBERADA", "Liberada"
        BLOQUEADA = "BLOQUEADA", "Bloqueada"
        CANCELADA = "CANCELADA", "Cancelada"

    FINAIS = {Status.LIBERADA, Status.BLOQUEADA, Status.CANCELADA}

    atividade = models.ForeignKey(
        "cadastros.Atividade", on_delete=models.PROTECT, related_name="pre_liberacoes"
    )
    trabalhador = models.ForeignKey(
        "cadastros.Trabalhador", on_delete=models.PROTECT, related_name="pre_liberacoes"
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pre_liberacoes_abertas"
    )
    local = models.CharField(max_length=120)
    numero_pt_os = models.CharField("nº da PT/OS", max_length=30, blank=True)
    exige_aprovacao = models.BooleanField(
        default=True, help_text="Cópia do rigor da atividade no momento da abertura."
    )
    status = models.CharField(
        max_length=22, choices=Status.choices, default=Status.EM_CONFERENCIA
    )
    aberta_em = models.DateTimeField(default=timezone.now)
    conferida_em = models.DateTimeField(null=True, blank=True)
    decidida_em = models.DateTimeField(null=True, blank=True)
    conferida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="pre_liberacoes_conferidas",
        help_text="Técnico ou gestor que fez a conferência física (nunca o próprio colaborador).",
    )
    decidida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="pre_liberacoes_decididas",
    )
    conferencia_fisica_confirmada = models.BooleanField(default=False)
    motivo = models.TextField(blank=True)
    snapshot = models.JSONField(null=True, blank=True)
    hash_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-aberta_em"]
        verbose_name = "pré-liberação"
        verbose_name_plural = "pré-liberações"
        indexes = [
            models.Index(fields=["trabalhador", "aberta_em"]),
            models.Index(fields=["atividade", "aberta_em"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.numero} {self.atividade.nome}"

    @property
    def numero(self):
        return f"PL-{self.pk:06d}" if self.pk else "PL-novo"

    @property
    def finalizada(self):
        return self.status in self.FINAIS

    @property
    def duracao(self):
        fim = self.decidida_em or (None if self.finalizada else timezone.now())
        if not fim:
            return None
        return fim - self.aberta_em

    @property
    def modo_label(self):
        return "Modo aprovação" if self.exige_aprovacao else "Modo registro"

    def save(self, *args, **kwargs):
        # Imutabilidade (RNF05): registro decidido não muda mais.
        if self.pk and not getattr(self, "_permitir_finalizacao", False):
            anterior = (
                PreLiberacao.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
            if anterior in self.FINAIS:
                raise ValidationError(
                    "Pré-liberação finalizada é imutável. Abra uma nova para corrigir."
                )
        super().save(*args, **kwargs)


class ConferenciaItem(models.Model):
    class Auto(models.TextChoices):
        OK = "OK", "Válido"
        NAO_ENTREGUE = "NAO_ENTREGUE", "Não entregue"
        VENCIDO = "VENCIDO", "Vencido"
        CA_VENCIDO = "CA_VENCIDO", "CA vencido"
        AVARIADO = "AVARIADO", "Avariado"
        EXTRAVIADO = "EXTRAVIADO", "Extraviado"

    class Fisico(models.TextChoices):
        PENDENTE = "PENDENTE", "A conferir"
        CONFORME = "CONFORME", "Conforme"
        AUSENTE = "AUSENTE", "Ausente"
        DANIFICADO = "DANIFICADO", "Danificado"
        VENCIDO = "VENCIDO", "Vencido"

    pre_liberacao = models.ForeignKey(PreLiberacao, on_delete=models.CASCADE, related_name="itens")
    tipo_epi = models.ForeignKey("epis.TipoEpi", on_delete=models.PROTECT, related_name="+")
    unidade = models.ForeignKey(
        "epis.UnidadeEpi", null=True, blank=True, on_delete=models.PROTECT,
        related_name="conferencias",
    )
    resultado_auto = models.CharField(max_length=14, choices=Auto.choices, default=Auto.NAO_ENTREGUE)
    motivo_auto = models.CharField(max_length=160, blank=True)
    resultado_fisico = models.CharField(
        max_length=12, choices=Fisico.choices, default=Fisico.PENDENTE
    )
    observacao = models.CharField("observação", max_length=300, blank=True)
    foto = models.FileField(upload_to="conferencias/%Y/%m/", null=True, blank=True)
    conferido_em = models.DateTimeField(null=True, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "item conferido"
        verbose_name_plural = "itens conferidos"

    def __str__(self):
        return f"{self.tipo_epi.nome} ({self.get_resultado_fisico_display()})"

    @property
    def auto_ok(self):
        return self.resultado_auto == self.Auto.OK

    @property
    def conforme(self):
        return self.auto_ok and self.resultado_fisico == self.Fisico.CONFORME

    @property
    def pendente(self):
        return self.resultado_fisico == self.Fisico.PENDENTE


class ChecklistResposta(models.Model):
    pre_liberacao = models.ForeignKey(
        PreLiberacao, on_delete=models.CASCADE, related_name="respostas"
    )
    item_modelo = models.ForeignKey(
        "cadastros.ChecklistItemModelo", on_delete=models.PROTECT, related_name="respostas"
    )
    resposta = models.BooleanField(null=True, blank=True)
    observacao = models.CharField("observação", max_length=300, blank=True)

    class Meta:
        ordering = ["item_modelo__ordem", "item_modelo_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pre_liberacao", "item_modelo"], name="uma_resposta_por_pergunta"
            )
        ]

    @property
    def nao_conforme(self):
        return self.item_modelo.bloqueante and self.resposta is False


class Assinatura(models.Model):
    class Papel(models.TextChoices):
        TRABALHADOR = "TRABALHADOR", "Colaborador (ciência)"
        CONFERENTE = "CONFERENTE", "Conferente (técnico de segurança)"
        RESPONSAVEL = "RESPONSAVEL", "Gestor de SST (aprovação)"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assinaturas",
        help_text="Usuário autenticado no aparelho em que a assinatura foi feita.",
    )
    entrega = models.ForeignKey(
        "epis.EntregaEpi", null=True, blank=True, on_delete=models.PROTECT,
        related_name="assinaturas",
    )
    pre_liberacao = models.ForeignKey(
        PreLiberacao, null=True, blank=True, on_delete=models.PROTECT,
        related_name="assinaturas",
    )
    papel = models.CharField(max_length=12, choices=Papel.choices)
    signatario_nome = models.CharField("nome de quem assinou", max_length=120)
    imagem = models.TextField(help_text="Imagem da assinatura (data URL).")
    hash_sha256 = models.CharField(max_length=64)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    assinado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["assinado_em"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(entrega__isnull=False, pre_liberacao__isnull=True)
                    | models.Q(entrega__isnull=True, pre_liberacao__isnull=False)
                ),
                name="assinatura_um_unico_vinculo",
            )
        ]

    def __str__(self):
        return f"{self.signatario_nome} ({self.get_papel_display()})"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Assinaturas não podem ser alteradas.")
        super().save(*args, **kwargs)
