from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from core import testutils as tu
from reposicao.models import SolicitacaoReposicao
from reposicao.services import solicitar_reposicao

from .codigo import canonico, codigo_valido, gerar_codigo
from .models import EntregaEpi, UnidadeEpi
from .services import avaliar_unidade, entregas_ativas, registrar_entrega

PNG = tu.png_dataurl()


class CodigoTests(TestCase):
    def test_digito_verificador(self):
        self.assertEqual(gerar_codigo(123), "EPI-000123-0")
        self.assertTrue(codigo_valido("EPI-000123-0"))
        self.assertTrue(codigo_valido("epi0001230"))
        self.assertFalse(codigo_valido("EPI-000123-5"))
        self.assertFalse(codigo_valido("EPI-000132-0"))  # dígitos trocados
        self.assertEqual(canonico(" epi 000123 0 "), "EPI-000123-0")

    def test_unidade_recebe_codigo_sequencial(self):
        u = tu.unidade(tu.tipo())
        self.assertEqual(u.codigo, gerar_codigo(u.pk))


class AvaliacaoTests(TestCase):
    def setUp(self):
        self.tipo = tu.tipo(vida_util=90)

    def test_regras(self):
        self.assertEqual(avaliar_unidade(tu.unidade(self.tipo))[0], "OK")
        self.assertEqual(avaliar_unidade(tu.unidade(self.tipo, dias_validade=-1))[0], "VENCIDO")
        self.assertEqual(avaliar_unidade(tu.unidade(self.tipo, status="AVARIADO"))[0], "AVARIADO")
        t2 = tu.tipo("Óculos", dias_ca=-3)
        self.assertEqual(avaliar_unidade(tu.unidade(t2))[0], "CA_VENCIDO")

    def test_vida_util_conta_da_entrega(self):
        t = tu.Trabalhador.objects.create(matricula="1", nome="A")
        por = tu.usuario("x", "ALMOX")
        e = tu.entregar(tu.unidade(self.tipo), t, por, dias_atras=100)
        resultado, motivo = avaliar_unidade(e.unidade, e)
        self.assertEqual(resultado, "VENCIDO")
        self.assertIn("Vida útil", motivo)


class EntregaTests(TestCase):
    def setUp(self):
        self.c = tu.cenario()

    def test_recusa_unidade_vencida_ou_ja_entregue(self):
        vencida = tu.unidade(self.c["luva"], dias_validade=-1)
        for u in (vencida, self.c["u_cap"]):
            with self.assertRaises(ValidationError):
                registrar_entrega(unidade=u, trabalhador=self.c["t"], usuario=self.c["almox"],
                                  assinatura_imagem=PNG, signatario_nome="João")

    def test_substituicao_encerra_a_unidade_com_problema_e_atende_pedido(self):
        u = self.c["u_luva"]
        u.validade = tu.hoje() - timedelta(days=1)
        u.save()
        sol = solicitar_reposicao(trabalhador=self.c["t"], tipo_epi=self.c["luva"], motivo="VENCIDO",
                                  usuario=self.c["op"], unidade=u)
        nova = tu.unidade(self.c["luva"])
        entrega = registrar_entrega(unidade=nova, trabalhador=self.c["t"], usuario=self.c["almox"],
                                    assinatura_imagem=PNG, signatario_nome="João Pereira",
                                    motivo=EntregaEpi.Motivo.SUBSTITUICAO)
        self.assertEqual([e.unidade for e in entregas_ativas(self.c["t"], self.c["luva"])], [nova])
        u.refresh_from_db()
        nova.refresh_from_db()
        sol.refresh_from_db()
        self.assertEqual(u.status, UnidadeEpi.Status.DESCARTADO)
        self.assertEqual(nova.status, UnidadeEpi.Status.ENTREGUE)
        self.assertEqual(sol.status, SolicitacaoReposicao.Status.ATENDIDA)
        self.assertEqual(sol.entrega, entrega)
        self.assertEqual(entrega.assinaturas.count(), 1)

    def test_perda_marca_extraviado_e_substituicao_nao_devolve_ao_estoque(self):
        u = self.c["u_cap"]
        solicitar_reposicao(trabalhador=self.c["t"], tipo_epi=self.c["capacete"], motivo="PERDA",
                            usuario=self.c["op"], unidade=u, observacao="Caiu do andaime no rio")
        u.refresh_from_db()
        self.assertEqual(u.status, UnidadeEpi.Status.EXTRAVIADO)
        self.assertEqual(avaliar_unidade(u)[0], "EXTRAVIADO")
        nova = tu.unidade(self.c["capacete"])
        registrar_entrega(unidade=nova, trabalhador=self.c["t"], usuario=self.c["almox"],
                          assinatura_imagem=PNG, signatario_nome="João Pereira",
                          motivo=EntregaEpi.Motivo.SUBSTITUICAO)
        u.refresh_from_db()
        self.assertEqual(u.status, UnidadeEpi.Status.EXTRAVIADO)
        self.assertEqual([e.unidade for e in entregas_ativas(self.c["t"], self.c["capacete"])], [nova])

    def test_avaria_informada_tira_de_uso_e_nao_duplica_pedido(self):
        u = self.c["u_cap"]
        a = solicitar_reposicao(trabalhador=self.c["t"], tipo_epi=self.c["capacete"],
                                motivo="DANIFICADO", usuario=self.c["op"], unidade=u,
                                observacao="Casco trincado")
        b = solicitar_reposicao(trabalhador=self.c["t"], tipo_epi=self.c["capacete"],
                                motivo="DANIFICADO", usuario=self.c["op"], unidade=u)
        self.assertEqual(a.pk, b.pk)
        u.refresh_from_db()
        self.assertEqual(u.status, UnidadeEpi.Status.AVARIADO)
