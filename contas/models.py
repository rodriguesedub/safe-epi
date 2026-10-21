from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Perfil(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        GESTOR_SST = "GESTOR_SST", "Gestor de SST"
        TECNICO_SST = "TECNICO_SST", "Técnico de Segurança"
        OPERACIONAL = "OPERACIONAL", "Colaborador"
        ALMOX = "ALMOX", "Almoxarifado"

    perfil = models.CharField(
        max_length=20, choices=Perfil.choices, default=Perfil.OPERACIONAL
    )
    trabalhador = models.OneToOneField(
        "cadastros.Trabalhador",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usuario",
        help_text="Vínculo obrigatório para colaboradores.",
    )

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    @property
    def nome_exibicao(self):
        return self.get_full_name() or self.username

    @property
    def perfil_curto(self):
        return {"ADMIN": "admin", "GESTOR_SST": "gestão de SST", "TECNICO_SST": "técnico de segurança",
                "OPERACIONAL": "colaborador", "ALMOX": "almoxarifado"}.get(self.perfil, self.perfil)

    @property
    def is_admin_safeepi(self):
        return self.is_superuser or self.perfil == self.Perfil.ADMIN

    @property
    def is_gestor(self):
        return self.is_admin_safeepi or self.perfil == self.Perfil.GESTOR_SST

    @property
    def is_tecnico(self):
        return self.perfil == self.Perfil.TECNICO_SST

    @property
    def is_conferente(self):
        """Quem pode fazer a conferência física: técnico de segurança ou gestor de SST."""
        return self.is_tecnico or self.is_gestor

    @property
    def is_almox(self):
        return self.is_admin_safeepi or self.perfil == self.Perfil.ALMOX

    @property
    def is_operacional(self):
        return self.perfil == self.Perfil.OPERACIONAL

    @property
    def is_campo(self):
        """Perfis que usam o sistema no celular, no local da atividade."""
        return self.is_operacional or self.is_tecnico

    def tem_perfil(self, *chaves):
        """chaves: 'gestor', 'tecnico', 'conferente', 'almox', 'operacional', 'admin'."""
        mapa = {
            "gestor": self.is_gestor,
            "tecnico": self.is_tecnico,
            "conferente": self.is_conferente,
            "almox": self.is_almox,
            "operacional": self.is_operacional,
            "admin": self.is_admin_safeepi,
        }
        return any(mapa.get(c, False) for c in chaves)
