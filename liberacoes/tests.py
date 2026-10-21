from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core import testutils as tu
from epis.models import EntregaEpi, UnidadeEpi
from epis.services import registrar_entrega
from reposicao.models import SolicitacaoReposicao

from . import services as sv
from .assinaturas import validar_imagem
from .models import Assinatura, ConferenciaItem, PreLiberacao

S = PreLiberacao.Status
PNG = tu.png_dataurl()


def conferir_tudo(pre, usuario, resultado="CONFORME", resposta=True):
    for item in pre.itens.all():
        sv.marcar_item(item, usuario=usuario, resultado_fisico=resultado)
    for r in pre.respostas.all():
        sv.responder_pergunta(r, usuario=usuario, valor=resposta)


class FluxoPreLiberacaoTests(TestCase):
    def setUp(self):
        self.c = tu.cenario(exige_aprovacao=True)
        self.tec = self.c["tecnico"]

    def abrir(self, usuario=None):
        return sv.abrir_pre_liberacao(atividade=self.c["atividade"], trabalhador=self.c["t"],
                                      usuario=usuario or self.c["op"], local="Torre 2")

    def concluir(self, pre, usuario=None, **kw):
        return sv.concluir_conferencia(pre, usuario=usuario or self.tec, assinatura_conferente=PNG,
                                       assinatura_colaborador=PNG,
                                       confirmou_fisico=kw.pop("confirmou", True), **kw)

    def test_gera_um_item_por_epi_e_vincula_entregas(self):
        pre = self.abrir()
        itens = list(pre.itens.all())
        self.assertEqual(len(itens), 2)
        self.assertTrue(all(i.resultado_auto == "OK" and i.unidade_id for i in itens))
        self.assertEqual(pre.respostas.count(), 1)

    def test_colaborador_nao_confere_os_proprios_epis(self):
        pre = self.abrir()
        item = pre.itens.first()
        self.assertFalse(sv.pode_conferir(self.c["op"], pre))
        with self.assertRaises(PermissionDenied):
            sv.marcar_item(item, usuario=self.c["op"], resultado_fisico="CONFORME")
        with self.assertRaises(PermissionDenied):
            sv.responder_pergunta(pre.respostas.first(), usuario=self.c["op"], valor=True)
        with self.assertRaises(PermissionDenied):
            sv.concluir_conferencia(pre, usuario=self.c["op"], assinatura_conferente=PNG,
                                    assinatura_colaborador=PNG, confirmou_fisico=True)
        # mas pode pedir a substituição de um EPI dele
        self.assertTrue(sv.pode_pedir_substituicao(self.c["op"], pre))
        # almoxarifado também não confere
        self.assertFalse(sv.pode_conferir(self.c["almox"], pre))

    def test_tecnico_confere_e_gestor_diferente_aprova_com_hash(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        self.assertEqual(pre.status, S.AGUARDANDO_APROVACAO)
        self.assertEqual(pre.conferida_por, self.tec)
        papeis = set(pre.assinaturas.values_list("papel", flat=True))
        self.assertEqual(papeis, {Assinatura.Papel.CONFERENTE, Assinatura.Papel.TRABALHADOR})
        ciencia = pre.assinaturas.get(papel=Assinatura.Papel.TRABALHADOR)
        self.assertEqual(ciencia.signatario_nome, "João Pereira")
        with self.assertRaises(PermissionDenied):  # técnico não aprova
            sv.decidir(pre, usuario=self.tec, liberar=True, motivo="", assinatura_imagem=PNG,
                       signatario_nome="Rodrigo")
        pre = sv.decidir(pre, usuario=self.c["gestor"], liberar=True, motivo="",
                         assinatura_imagem=PNG, signatario_nome="Mariana Costa")
        self.assertEqual(pre.status, S.LIBERADA)
        self.assertEqual(len(pre.hash_sha256), 64)
        self.assertTrue(sv.integridade_ok(pre))
        self.assertEqual(len(pre.snapshot["assinaturas"]), 3)
        self.assertEqual(pre.snapshot["conferida_por"], "tecnico")

    def test_gestor_que_conferiu_nao_aprova_a_mesma(self):
        pre = self.abrir()
        conferir_tudo(pre, self.c["gestor"])
        pre = self.concluir(pre, usuario=self.c["gestor"])
        self.assertEqual(pre.status, S.AGUARDANDO_APROVACAO)
        self.assertFalse(sv.pode_decidir(self.c["gestor"], pre))
        with self.assertRaises(PermissionDenied):
            sv.decidir(pre, usuario=self.c["gestor"], liberar=True, motivo="",
                       assinatura_imagem=PNG, signatario_nome="Mariana")

    def test_modo_registro_libera_na_conclusao_do_tecnico(self):
        a = self.c["atividade"]
        a.exige_aprovacao = False
        a.save()
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        self.assertEqual(pre.status, S.LIBERADA)
        self.assertEqual(pre.decidida_por, self.tec)

    def test_troca_de_rigor_nao_afeta_pre_liberacao_aberta(self):
        pre = self.abrir()
        a = self.c["atividade"]
        a.exige_aprovacao = False
        a.save()
        conferir_tudo(pre, self.tec)
        self.assertEqual(self.concluir(pre).status, S.AGUARDANDO_APROVACAO)

    def test_epi_vencido_bloqueia_e_abre_reposicao(self):
        u = self.c["u_luva"]
        u.validade = tu.hoje() - timedelta(days=2)
        u.save()
        pre = self.abrir()
        item = pre.itens.get(tipo_epi=self.c["luva"])
        self.assertEqual(item.resultado_auto, ConferenciaItem.Auto.VENCIDO)
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        self.assertEqual(pre.status, S.BLOQUEADA)
        self.assertIn("Luva", pre.motivo)
        sol = SolicitacaoReposicao.objects.get(trabalhador=self.c["t"], tipo_epi=self.c["luva"])
        self.assertEqual(sol.pre_liberacao, pre)
        self.assertEqual(sol.motivo, "VENCIDO")

    def test_ca_vencido_e_epi_nao_entregue_sao_detectados(self):
        cap = self.c["capacete"]
        cap.validade_ca = tu.hoje() - timedelta(days=1)
        cap.save()
        EntregaEpi.objects.filter(unidade=self.c["u_luva"]).delete()
        pre = self.abrir()
        resultados = {i.tipo_epi.nome: i.resultado_auto for i in pre.itens.all()}
        self.assertEqual(resultados, {"Capacete": "CA_VENCIDO", "Luva": "NAO_ENTREGUE"})

    def test_substituicao_no_local_revalida_e_zera_conferencia_do_item(self):
        u = self.c["u_luva"]
        u.validade = tu.hoje() - timedelta(days=2)
        u.save()
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        nova = tu.unidade(self.c["luva"])
        registrar_entrega(unidade=nova, trabalhador=self.c["t"], usuario=self.c["almox"],
                          assinatura_imagem=PNG, signatario_nome="João Pereira",
                          motivo=EntregaEpi.Motivo.SUBSTITUICAO)
        sv.validar_itens(pre)
        item = pre.itens.get(tipo_epi=self.c["luva"])
        self.assertEqual(item.unidade, nova)
        self.assertEqual(item.resultado_auto, "OK")
        self.assertEqual(item.resultado_fisico, "PENDENTE")
        u.refresh_from_db()
        self.assertEqual(u.status, UnidadeEpi.Status.DESCARTADO)

    def test_pergunta_bloqueante_respondida_nao_bloqueia(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec, resposta=False)
        self.assertEqual(self.concluir(pre).status, S.BLOQUEADA)

    def test_ausente_bloqueia_sem_virar_perda_automatica(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        sv.marcar_item(pre.itens.get(tipo_epi=self.c["capacete"]), usuario=self.tec,
                       resultado_fisico="AUSENTE")
        self.assertEqual(self.concluir(pre).status, S.BLOQUEADA)
        self.assertFalse(SolicitacaoReposicao.objects.filter(motivo="PERDA").exists())
        self.c["u_cap"].refresh_from_db()
        self.assertEqual(self.c["u_cap"].status, UnidadeEpi.Status.ENTREGUE)

    def test_exige_conferencia_completa_e_confirmacao_fisica(self):
        pre = self.abrir()
        with self.assertRaises(ValidationError):
            self.concluir(pre)
        conferir_tudo(pre, self.tec)
        with self.assertRaises(ValidationError):
            self.concluir(pre, confirmou=False)

    def test_exige_as_duas_assinaturas(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        with self.assertRaises(ValidationError):
            sv.concluir_conferencia(pre, usuario=self.tec, assinatura_conferente=PNG,
                                    assinatura_colaborador="", confirmou_fisico=True)

    def test_danificado_tira_unidade_de_uso(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        item = pre.itens.get(tipo_epi=self.c["capacete"])
        sv.marcar_item(item, usuario=self.tec, resultado_fisico="DANIFICADO")
        self.assertEqual(self.concluir(pre).status, S.BLOQUEADA)
        self.c["u_cap"].refresh_from_db()
        self.assertEqual(self.c["u_cap"].status, UnidadeEpi.Status.AVARIADO)

    def test_bloqueio_pelo_gestor_exige_motivo(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        with self.assertRaises(ValidationError):
            sv.decidir(pre, usuario=self.c["gestor"], liberar=False, motivo="curto",
                       assinatura_imagem=PNG, signatario_nome="Mariana")
        pre = sv.decidir(pre, usuario=self.c["gestor"], liberar=False,
                         motivo="Vento acima do limite para trabalho em altura",
                         assinatura_imagem=PNG, signatario_nome="Mariana")
        self.assertEqual(pre.status, S.BLOQUEADA)

    def test_aprovacao_reavalia_epi_que_venceu_depois_da_conferencia(self):
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        u = self.c["u_cap"]
        u.validade = tu.hoje() - timedelta(days=1)
        u.save()
        with self.assertRaises(ValidationError):
            sv.decidir(pre, usuario=self.c["gestor"], liberar=True, motivo="",
                       assinatura_imagem=PNG, signatario_nome="Mariana")

    def test_registro_decidido_e_imutavel_e_adulteracao_e_detectada(self):
        a = self.c["atividade"]
        a.exige_aprovacao = False
        a.save()
        pre = self.abrir()
        conferir_tudo(pre, self.tec)
        pre = self.concluir(pre)
        pre.local = "Outro"
        with self.assertRaises(ValidationError):
            pre.save()
        with self.assertRaises(ValidationError):
            ass = pre.assinaturas.first()
            ass.signatario_nome = "Outro"
            ass.save()
        snap = dict(pre.snapshot)
        snap["local"] = "Adulterado"
        PreLiberacao.objects.filter(pk=pre.pk).update(snapshot=snap)
        pre.refresh_from_db()
        self.assertFalse(sv.integridade_ok(pre))

    def test_colaborador_so_solicita_para_si(self):
        outro = tu.Trabalhador.objects.create(matricula="T999", nome="Outra Pessoa")
        with self.assertRaises(PermissionDenied):
            sv.abrir_pre_liberacao(atividade=self.c["atividade"], trabalhador=outro,
                                   usuario=self.c["op"], local="X")
        # o técnico abre para qualquer colaborador
        pre = sv.abrir_pre_liberacao(atividade=self.c["atividade"], trabalhador=self.c["t"],
                                     usuario=self.tec, local="X")
        self.assertEqual(pre.solicitante, self.tec)

    def test_cancelamento(self):
        pre = self.abrir()
        sv.cancelar(pre, usuario=self.c["op"], motivo="Chuva forte, atividade adiada")
        pre.refresh_from_db()
        self.assertEqual(pre.status, S.CANCELADA)


class AssinaturaTests(TestCase):
    def test_valida_png_real_e_recusa_vazio(self):
        self.assertTrue(validar_imagem(PNG).startswith("data:image/png"))
        for ruim in ["", "data:image/jpeg;base64,AAAA", "data:image/png;base64,@@@",
                     "data:image/png;base64,iVBORw0KGgo="]:
            with self.assertRaises(ValidationError):
                validar_imagem(ruim)
