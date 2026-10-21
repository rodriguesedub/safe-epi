from django.db import models


class Trabalhador(models.Model):
    matricula = models.CharField("matrícula", max_length=20, unique=True)
    nome = models.CharField(max_length=120)
    funcao = models.CharField("função", max_length=80, blank=True)
    setor = models.CharField(max_length=80, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "trabalhador"
        verbose_name_plural = "trabalhadores"

    def __str__(self):
        return f"{self.nome} ({self.matricula})"


class Atividade(models.Model):
    class NivelRisco(models.TextChoices):
        BAIXO = "BAIXO", "Baixo"
        MEDIO = "MEDIO", "Médio"
        ALTO = "ALTO", "Alto"

    nome = models.CharField(max_length=120)
    descricao = models.TextField("descrição", blank=True)
    nr_referencia = models.CharField(
        "NR de referência", max_length=40, blank=True, help_text="Ex.: NR-35"
    )
    nivel_risco = models.CharField(
        "nível de risco", max_length=10, choices=NivelRisco.choices,
        default=NivelRisco.MEDIO,
    )
    exige_aprovacao = models.BooleanField(
        "exige aprovação do gestor de SST",
        default=True,
        help_text=(
            "Modo aprovação: o gestor de SST libera ou bloqueia depois da "
            "conferência. Desmarcado = modo registro: a conferência 100% "
            "conforme libera a atividade. Vale para novas pré-liberações."
        ),
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "atividade"
        verbose_name_plural = "atividades"

    def __str__(self):
        return f"{self.nome} ({self.nr_referencia})" if self.nr_referencia else self.nome

    @property
    def modo_label(self):
        return "Modo aprovação" if self.exige_aprovacao else "Modo registro"


class AtividadeEpiRequisito(models.Model):
    atividade = models.ForeignKey(
        Atividade, on_delete=models.CASCADE, related_name="requisitos"
    )
    tipo_epi = models.ForeignKey(
        "epis.TipoEpi", on_delete=models.PROTECT, related_name="requisitos",
        verbose_name="tipo de EPI",
    )
    quantidade = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "EPI obrigatório"
        verbose_name_plural = "EPIs obrigatórios (matriz atividade × EPI)"
        constraints = [
            models.UniqueConstraint(
                fields=["atividade", "tipo_epi"], name="requisito_unico_por_atividade"
            )
        ]

    def __str__(self):
        return f"{self.atividade.nome}: {self.tipo_epi.nome} × {self.quantidade}"


class ChecklistItemModelo(models.Model):
    atividade = models.ForeignKey(
        Atividade, on_delete=models.CASCADE, related_name="perguntas"
    )
    texto = models.CharField(max_length=200, help_text="Ex.: PT emitida e assinada?")
    bloqueante = models.BooleanField(
        default=True, help_text="Resposta 'Não' bloqueia a liberação."
    )
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "pergunta do checklist"
        verbose_name_plural = "perguntas do checklist"

    def __str__(self):
        return self.texto
