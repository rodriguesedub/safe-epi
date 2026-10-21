"""Testes de ponta a ponta das telas, sobre os dados de demonstração."""
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from cadastros.models import Atividade, Trabalhador
from core.testutils import png_dataurl
from epis.models import UnidadeEpi
from liberacoes.models import PreLiberacao


class TelasDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def entrar(self, username):
        self.assertTrue(self.client.login(username=username, password="safeepi123"))

    def test_todas_as_telas_abrem_para_cada_perfil(self):
        joao = Trabalhador.objects.get(matricula="T1001")
        telas = {
            "operador": ["/", "/pre-liberacoes/", "/pre-liberacoes/nova/", "/epis/meus/",
                         "/reposicoes/nova/", f"/painel/colaboradores/{joao.pk}/ficha-epi/"],
            "tecnico": ["/", "/pre-liberacoes/", "/pre-liberacoes/nova/", "/painel/busca/?trabalhador=Jo",
                        f"/painel/colaboradores/{joao.pk}/", f"/painel/colaboradores/{joao.pk}/ficha-epi/"],
            "gestor": ["/painel/", "/painel/estatisticas/", "/painel/estatisticas/?dias=30",
                       "/painel/estatisticas/?dias=180", "/pre-liberacoes/?aba=todas",
                       "/painel/busca/?trabalhador=Jo", "/alertas/", "/painel/conformidade/",
                       "/painel/conformidade/?formato=csv", "/auditoria/", "/epis/", "/cadastros/importar/",
                       "/admin/", f"/painel/colaboradores/{joao.pk}/ficha-epi/"],
            "almox": ["/", "/epis/entregar/", "/reposicoes/", "/epis/", "/alertas/",
                      "/alertas/compras.csv", "/cadastros/importar/", "/admin/"],
        }
        for usuario, urls in telas.items():
            self.entrar(usuario)
            for url in urls:
                with self.subTest(usuario=usuario, url=url):
                    r = self.client.get(url, follow=True)
                    self.assertEqual(r.status_code, 200)
        for usuario in ("gestor", "tecnico"):
            self.entrar(usuario)
            for p in PreLiberacao.objects.all()[:12]:
                with self.subTest(usuario=usuario, pre=p.pk):
                    self.assertEqual(self.client.get(f"/pre-liberacoes/{p.pk}/").status_code, 200)

    def test_perfis_sem_acesso_recebem_403(self):
        self.entrar("operador")
        for url in ["/painel/", "/painel/estatisticas/", "/auditoria/", "/reposicoes/", "/epis/entregar/",
                    "/painel/busca/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        outra = PreLiberacao.objects.exclude(trabalhador__matricula="T1001").first()
        self.assertEqual(self.client.get(f"/pre-liberacoes/{outra.pk}/").status_code, 403)
        outro = Trabalhador.objects.exclude(matricula="T1001").first()
        self.assertEqual(self.client.get(f"/painel/colaboradores/{outro.pk}/ficha-epi/").status_code, 403)
        self.entrar("tecnico")
        for url in ["/painel/estatisticas/", "/auditoria/", "/epis/entregar/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_roteiro_do_tutorial(self):
        """O mesmo caminho do tutorial: João pede, Paulo troca, Rodrigo confere, Mariana aprova."""
        # 1. João abre a NR-35: o talabarte vencido aparece barrado, e ele mesmo não confere nada
        self.entrar("operador")
        altura = Atividade.objects.get(nr_referencia="NR-35")
        r = self.client.post("/pre-liberacoes/nova/", {"atividade": altura.pk, "local": "Torre 2",
                                                      "numero_pt_os": "PT-2026-2107"})
        pre = PreLiberacao.objects.latest("aberta_em")
        self.assertRedirects(r, f"/pre-liberacoes/{pre.pk}/")
        item = pre.itens.get(tipo_epi__nome__startswith="Talabarte")
        self.assertEqual(item.resultado_auto, "VENCIDO")
        tela = self.client.get(f"/pre-liberacoes/{pre.pk}/")
        self.assertContains(tela, "Vencido em")
        self.assertContains(tela, "CA 38912")
        self.assertNotContains(tela, 'name="assinatura_conferente"')
        r = self.client.post(f"/pre-liberacoes/{pre.pk}/itens/{item.pk}/", {"resultado": "CONFORME"},
                             HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 403)
        self.client.post(f"/pre-liberacoes/{pre.pk}/itens/{item.pk}/substituicao/")

        # 2. Paulo atende o pedido e entrega o talabarte novo, com a assinatura do João
        self.entrar("almox")
        self.assertContains(self.client.get("/"), f'data-sol-pre="{pre.pk}"')
        novo = UnidadeEpi.objects.filter(tipo=item.tipo_epi, status="ESTOQUE", validade__isnull=False
                                         ).order_by("-validade").first()
        r = self.client.post("/epis/entregar/", {
            "trabalhador": pre.trabalhador_id, "tipo": item.tipo_epi_id, "unidade": novo.pk,
            "motivo": "SUBSTITUICAO", "signatario_nome": "João Pereira",
            "assinatura": png_dataurl(), "next": f"/pre-liberacoes/{pre.pk}/"})
        self.assertRedirects(r, f"/pre-liberacoes/{pre.pk}/", fetch_redirect_response=False)

        # 3. Rodrigo confere tudo no local (via HTMX), responde o checklist e colhe as duas assinaturas
        self.entrar("tecnico")
        self.assertContains(self.client.get("/"), f'data-pre="{pre.pk}"')
        self.assertContains(self.client.get(f"/pre-liberacoes/{pre.pk}/"), 'name="assinatura_colaborador"')
        for it in pre.itens.all():
            r = self.client.post(f"/pre-liberacoes/{pre.pk}/itens/{it.pk}/", {"resultado": "CONFORME"},
                                 HTTP_HX_REQUEST="true")
            self.assertContains(r, 'hx-swap-oob="true"')
        for resp in pre.respostas.all():
            self.client.post(f"/pre-liberacoes/{pre.pk}/perguntas/{resp.pk}/", {"valor": "sim"},
                             HTTP_HX_REQUEST="true")
        self.client.post(f"/pre-liberacoes/{pre.pk}/concluir/", {
            "confirmou_fisico": "on", "assinatura_conferente": png_dataurl(),
            "assinatura_colaborador": png_dataurl(), "nome_colaborador": "João Pereira"})
        pre.refresh_from_db()
        self.assertEqual(pre.status, "AGUARDANDO_APROVACAO")
        self.assertEqual(pre.conferida_por.username, "tecnico")
        self.assertEqual(pre.assinaturas.count(), 2)

        # 4. Mariana decide; quem conferiu não poderia aprovar
        self.entrar("gestor")
        self.assertContains(self.client.get("/painel/"), "Conferida por Rodrigo Teixeira")
        self.client.post(f"/pre-liberacoes/{pre.pk}/decidir/", {
            "decisao": "liberar", "signatario_nome": "Mariana Costa", "assinatura": png_dataurl()})
        pre.refresh_from_db()
        self.assertEqual(pre.status, "LIBERADA")
        self.assertContains(self.client.get(f"/pre-liberacoes/{pre.pk}/"), "Integridade verificada")
        self.assertEqual(self.client.get(f"/pre-liberacoes/{pre.pk}/comprovante/").status_code, 200)

    def test_estatisticas_para_o_gestor(self):
        self.entrar("gestor")
        r = self.client.get("/painel/estatisticas/")
        for texto in ("Quanto há de cada EPI", "Quem mais danifica", "Quem mais perde",
                      "Colaboradores com EPI fora da validade", "Marcos Oliveira", "Lucas Ferreira",
                      "Bruna Carvalho", "CA 36299 vencido"):
            self.assertContains(r, texto)

    def test_ca_aparece_para_cada_perfil(self):
        self.entrar("operador")
        self.assertContains(self.client.get("/"), "CA 38912")
        self.assertContains(self.client.get("/epis/meus/"), 'class="ca')
        self.entrar("almox")
        self.assertContains(self.client.get("/"), 'class="ca')
        self.entrar("tecnico")
        carlos = PreLiberacao.objects.filter(status="EM_CONFERENCIA").first()
        self.assertContains(self.client.get(f"/pre-liberacoes/{carlos.pk}/"), 'class="ca')

    def test_tutorial_comeca_com_dados_novos(self):
        r = self.client.get("/contas/entrar/")
        self.assertContains(r, 'data-tour-inicio="auto"')
        self.assertContains(r, "js/tour.js?v=")
        with mock.patch("core.views.call_command") as recriar:
            r = self.client.post("/demo/iniciar/", {"modo": "auto", "vel": "1.5", "contagem": "0"})
        recriar.assert_called_once_with("seed_demo", reset=True, verbosity=0)
        self.assertRedirects(r, "/?tour=auto&vel=1.5&contagem=0", fetch_redirect_response=False)
        self.assertContains(self.client.get("/"), 'data-usuario="operador"')
        with mock.patch("core.views.call_command"):
            r = self.client.post("/demo/iniciar/", {"modo": "qualquer"})
        self.assertRedirects(r, "/?tour=guiado", fetch_redirect_response=False)

    @override_settings(SAFEEPI={"ALERTA_DIAS": [30, 15, 7], "DEMO_MODE": False, "FOTO_MAX_BYTES": 5 * 1024 * 1024})
    def test_sem_modo_demonstracao_nao_ha_tutorial(self):
        self.assertEqual(self.client.post("/demo/iniciar/", {"modo": "auto"}).status_code, 404)
        self.assertNotContains(self.client.get("/contas/entrar/"), "tour.js")

    def test_api_e_pwa(self):
        self.entrar("almox")
        u = UnidadeEpi.objects.first()
        r = self.client.get(f"/api/v1/epis/{u.codigo.replace('-', '').lower()}/")
        self.assertEqual(r.json()["codigo"], u.codigo)
        self.assertEqual(self.client.get("/api/v1/epis/EPI-999999-9/").status_code, 404)
        self.assertEqual(self.client.get("/manifest.webmanifest").json()["short_name"], "SAFEEPI")
        sw = self.client.get("/sw.js").content.decode()
        self.assertIn("caches.open", sw)
        self.assertIn("?v=", sw)
        self.assertEqual(self.client.get("/offline/").status_code, 200)
