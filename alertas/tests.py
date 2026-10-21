from datetime import timedelta

from django.core import mail
from django.test import TestCase

from core import testutils as tu

from .models import Alerta
from .services import gerar_alertas


class AlertasTests(TestCase):
    def test_faixas_e_resolucao(self):
        tu.usuario("g", "GESTOR_SST")
        t = tu.tipo("Talabarte", dias_ca=20)
        u10 = tu.unidade(t, dias_validade=10)
        u_venc = tu.unidade(t, dias_validade=-3)
        tu.unidade(t, dias_validade=200)
        r = gerar_alertas()
        self.assertEqual(r["criados"], 3)
        self.assertEqual(Alerta.objects.get(unidade=u10).dias_antecedencia, 15)
        self.assertEqual(Alerta.objects.get(unidade=u_venc).dias_antecedencia, 0)
        self.assertEqual(Alerta.objects.get(tipo="VALIDADE_CA").dias_antecedencia, 30)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alertas de vencimento", mail.outbox[0].subject)

        u_venc.status = "DESCARTADO"
        u_venc.save()
        r = gerar_alertas(enviar_email=False)
        self.assertEqual(r["resolvidos"], 1)
        self.assertEqual(r["criados"], 0)

    def test_vida_util(self):
        t = tu.tipo("Luva", vida_util=90)
        trab = tu.Trabalhador.objects.create(matricula="1", nome="A")
        e = tu.entregar(tu.unidade(t, dias_validade=None), trab, tu.usuario("a", "ALMOX"),
                        dias_atras=80)
        gerar_alertas(enviar_email=False)
        a = Alerta.objects.get(tipo="VIDA_UTIL")
        self.assertEqual(a.vence_em, e.fim_vida_util)
        self.assertEqual(a.dias_antecedencia, 15)
