"""Dados de demonstração do SAFEEPI.

Cria usuários, trabalhadores, EPIs, atividades e cerca de 30 dias de histórico
realista (gerado pelas mesmas regras de negócio, com um relógio simulado), além
do cenário preparado para o roteiro de apresentação do README.

    python manage.py seed_demo            # cria (falha se já houver dados)
    python manage.py seed_demo --se-vazio # só cria se o banco estiver vazio
    python manage.py seed_demo --reset    # apaga tudo e recria
"""
import base64
import math
import random
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from unittest import mock

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from alertas.services import gerar_alertas
from cadastros.models import Atividade, AtividadeEpiRequisito, ChecklistItemModelo, Trabalhador
from contas.models import Usuario
from contas.services import configurar_grupos, grupo_do_perfil
from epis.models import EntregaEpi, TipoEpi, UnidadeEpi
from epis.services import registrar_entrega
from liberacoes import services as lib
from liberacoes.assinaturas import criar_assinatura
from liberacoes.models import Assinatura, PreLiberacao
from reposicao.models import SolicitacaoReposicao

SENHA = "safeepi123"
_now_real = timezone.now


class Relogio:
    """Relógio simulado: as regras usam timezone.now(), então o histórico nasce coerente."""

    def __init__(self, inicio):
        self.atual = inicio

    def __call__(self):
        return self.atual

    def avancar(self, minutos):
        self.atual += timedelta(minutes=minutos)


@contextmanager
def no_tempo(momento):
    relogio = Relogio(momento)
    with mock.patch("django.utils.timezone.now", relogio):
        yield relogio


def assinatura_svg(nome):
    """Rabisco determinístico com cara de assinatura, para os dados de exemplo."""
    rnd = random.Random(nome)
    pontos = []
    x = 14
    for i in range(46):
        x += rnd.uniform(5, 9)
        y = 46 + 18 * math.sin(i / 2.2 + rnd.uniform(-0.4, 0.4)) * rnd.uniform(0.5, 1.1)
        pontos.append(f"{x:.1f},{y:.1f}")
    traco = f"{pontos[-1].split(',')[0]},62 {14 + rnd.uniform(0, 30):.1f},70"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 90">'
        f'<polyline points="{" ".join(pontos)}" fill="none" stroke="#1C2430" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<polyline points="{traco}" fill="none" stroke="#1C2430" stroke-width="1.6"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


class Command(BaseCommand):
    help = "Cria dados de demonstração e o cenário do roteiro de apresentação."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Apaga todos os dados antes.")
        parser.add_argument("--se-vazio", action="store_true",
                            help="Não faz nada se já existirem usuários.")

    def handle(self, *args, **opts):
        if opts["reset"]:
            call_command("flush", interactive=False, verbosity=0)
        elif Usuario.objects.exists():
            versao_antiga = (Usuario.objects.filter(username__in=["operador", "gestor"]).count() == 2
                             and not Usuario.objects.filter(username="tecnico").exists())
            if opts["se_vazio"] and versao_antiga:
                self.stdout.write("Dados de demonstração de uma versão anterior; recriando.")
                call_command("flush", interactive=False, verbosity=0)
            elif opts["se_vazio"]:
                self.stdout.write("Banco já tem dados; nada a fazer (use --reset para recriar).")
                return
            else:
                raise CommandError("O banco já tem dados. Use --reset para apagar e recriar.")
        self.rnd = random.Random(2026)
        self.hoje = timezone.localdate()
        with transaction.atomic():
            self._base()
            self._estoque_e_entregas()
            self._ocorrencias()
            self._historico()
            self._cenario_atual()
        gerar_alertas(enviar_email=False)
        self._resumo()

    # ------------------------------------------------------------------ base
    def _momento(self, dias_atras, hora=8, minuto=0):
        d = self.hoje - timedelta(days=dias_atras)
        return timezone.make_aware(datetime.combine(d, time(hora, minuto)))

    def _base(self):
        configurar_grupos()
        self.t = {}
        dados = [
            ("T1001", "João Pereira", "Montador de andaimes", "Manutenção", "altura"),
            ("T1002", "Ana Souza", "Eletricista", "Utilidades", "eletrica"),
            ("T1003", "Carlos Lima", "Técnico de manutenção", "Manutenção", "altura"),
            ("T1004", "Fernanda Rocha", "Eletricista", "Utilidades", "eletrica"),
            ("T1005", "Rafael Alves", "Soldador", "Caldeiraria", "producao"),
            ("T1006", "Juliana Martins", "Operadora de produção", "Produção", "producao"),
            ("T1007", "Marcos Oliveira", "Montador de andaimes", "Manutenção", "altura"),
            ("T1008", "Patrícia Gomes", "Inspetora de qualidade", "Produção", "producao"),
            ("T1009", "Lucas Ferreira", "Ajudante geral", "Manutenção", "altura"),
            ("T1010", "Bruna Carvalho", "Operadora de empilhadeira", "Logística", "producao"),
        ]
        self.perfil_trab = {}
        for mat, nome, funcao, setor, perfil in dados:
            self.t[mat] = Trabalhador.objects.create(matricula=mat, nome=nome, funcao=funcao, setor=setor)
            self.perfil_trab[mat] = perfil

        def criar(username, nome, sobrenome, perfil, trab=None, **extra):
            u = Usuario.objects.create_user(
                username=username, password=SENHA, first_name=nome, last_name=sobrenome,
                email=f"{username}@empresa-demo.com.br", perfil=perfil, trabalhador=trab, **extra)
            grupo = grupo_do_perfil(perfil)
            if grupo:
                from django.contrib.auth.models import Group
                u.groups.add(Group.objects.get(name=grupo))
            return u

        self.admin = criar("admin", "Admin", "", Usuario.Perfil.ADMIN, is_staff=True, is_superuser=True)
        self.gestor = criar("gestor", "Mariana", "Costa", Usuario.Perfil.GESTOR_SST, is_staff=True)
        self.almox = criar("almox", "Paulo", "Mendes", Usuario.Perfil.ALMOX, is_staff=True)
        self.tecnico = criar("tecnico", "Rodrigo", "Teixeira", Usuario.Perfil.TECNICO_SST)
        self.joao = criar("operador", "João", "Pereira", Usuario.Perfil.OPERACIONAL, self.t["T1001"])
        self.ana = criar("operador2", "Ana", "Souza", Usuario.Perfil.OPERACIONAL, self.t["T1002"])
        self.usuario_de = {"T1001": self.joao, "T1002": self.ana}

        h = self.hoje
        def tipo(chave, nome, cat, ca, dias_ca, vida=None, **extra):
            return chave, TipoEpi.objects.create(
                nome=nome, categoria=cat, numero_ca=ca, validade_ca=h + timedelta(days=dias_ca),
                vida_util_dias=vida, **extra)
        self.tp = dict([
            tipo("capacete", "Capacete de segurança classe B com jugular", "CABECA", "41201", 620),
            tipo("cinto", "Cinturão de segurança tipo paraquedista", "QUEDA", "38455", 510),
            tipo("talabarte", "Talabarte duplo com absorvedor de energia", "QUEDA", "38912", 20),
            tipo("luva_vaqueta", "Luva de vaqueta", "MAOS", "29034", 400, vida=90),
            tipo("luva_isolante", "Luva isolante de borracha classe 0", "MAOS", "33780", 700, inspecao_dias=180),
            tipo("oculos", "Óculos de proteção incolor", "OLHOS_FACE", "25516", 365, vida=180),
            tipo("protetor", "Protetor auricular tipo concha", "AUDITIVA", "27740", 800),
            tipo("botina", "Botina de segurança sem biqueira metálica", "PES", "44102", 900, vida=365),
            tipo("vestimenta", "Vestimenta antichama (FR) para risco elétrico", "CORPO", "40188", 450),
            tipo("pff2", "Respirador PFF2", "RESPIRATORIA", "36299", -10, rastreio_individual=False),
        ])

        def atividade(nome, nr, risco, aprovacao, desc, epis, perguntas):
            a = Atividade.objects.create(nome=nome, nr_referencia=nr, nivel_risco=risco,
                                         exige_aprovacao=aprovacao, descricao=desc)
            for e in epis:
                AtividadeEpiRequisito.objects.create(atividade=a, tipo_epi=self.tp[e])
            for i, (texto, bloq) in enumerate(perguntas):
                ChecklistItemModelo.objects.create(atividade=a, texto=texto, bloqueante=bloq, ordem=i)
            return a

        self.altura = atividade(
            "Trabalho em altura: montagem de andaime", "NR-35", "ALTO", True,
            "Montagem e desmontagem de andaimes acima de 2 m.",
            ["capacete", "cinto", "talabarte", "luva_vaqueta", "botina"],
            [("Permissão de Trabalho (PT) emitida e assinada?", True),
             ("APR revisada com a equipe no local?", True),
             ("Treinamento NR-35 do trabalhador dentro da validade?", True),
             ("Área abaixo isolada e sinalizada?", True)])
        self.eletrica = atividade(
            "Manutenção elétrica em baixa tensão", "NR-10", "ALTO", True,
            "Intervenção em painéis e circuitos até 1.000 V.",
            ["capacete", "luva_isolante", "oculos", "vestimenta", "botina"],
            [("Circuito desenergizado, bloqueado e etiquetado (LOTO)?", True),
             ("Ausência de tensão testada no ponto de trabalho?", True),
             ("Treinamento NR-10 dentro da validade?", True)])
        self.rotina = atividade(
            "Inspeção de rotina na área de produção", "NR-6", "BAIXO", False,
            "Ronda de inspeção sem intervenção em equipamentos.",
            ["capacete", "oculos", "protetor", "botina"],
            [("Rota combinada com o supervisor do turno?", False)])

    # ------------------------------------------------------------------ EPIs
    def _unidade(self, chave, dias_validade, status=UnidadeEpi.Status.ESTOQUE, tamanho=""):
        tamanhos = {"botina": ["39", "40", "41", "42", "43"], "luva_vaqueta": ["9", "10"],
                    "luva_isolante": ["9", "10"], "vestimenta": ["M", "G", "GG"], "cinto": ["M", "G"]}
        return UnidadeEpi.objects.create(
            tipo=self.tp[chave], status=status,
            validade=self.hoje + timedelta(days=dias_validade) if dias_validade is not None else None,
            fabricacao=self.hoje - timedelta(days=self.rnd.randint(60, 400)),
            serie_lote=f"L{self.rnd.randint(2400, 2699)}-{self.rnd.randint(10, 99)}",
            tamanho=tamanho or self.rnd.choice(tamanhos.get(chave, ["U"])),
        )

    def _entregar(self, unidade, mat, dias_atras):
        unidade.status = UnidadeEpi.Status.ENTREGUE
        unidade.save(update_fields=["status"])
        quando = self._momento(dias_atras, self.rnd.randint(7, 15), self.rnd.randint(0, 59))
        e = EntregaEpi.objects.create(unidade=unidade, trabalhador=self.t[mat], entregue_por=self.almox,
                                      entregue_em=quando)
        criar_assinatura(usuario=self.almox, papel=Assinatura.Papel.TRABALHADOR,
                         signatario_nome=self.t[mat].nome, imagem=assinatura_svg(self.t[mat].nome),
                         entrega=e, validar=False, assinado_em=quando)
        return e

    def _estoque_e_entregas(self):
        kits = {
            "altura": ["capacete", "cinto", "talabarte", "luva_vaqueta", "botina", "oculos", "protetor"],
            "eletrica": ["capacete", "luva_isolante", "oculos", "vestimenta", "botina", "protetor"],
            "producao": ["capacete", "oculos", "protetor", "botina"],
        }
        idade = {"luva_vaqueta": (35, 70), "oculos": (35, 150), "botina": (35, 300)}
        planejados = {(mat, chave) for mat, eventos in self.OCORRENCIAS.items() for chave, _, _ in eventos}
        for mat, perfil in self.perfil_trab.items():
            for chave in kits[perfil]:
                validade = self.rnd.randint(240, 1000)
                dias = self.rnd.randint(*idade.get(chave, (35, 330)))
                if (mat, chave) in planejados:
                    dias = self.rnd.randint(185, 200)  # antes da primeira ocorrência
                # Casos preparados para a demonstração
                if mat == "T1001" and chave == "talabarte":
                    validade, dias = -3, 140      # vence 3 dias atrás: bloqueia o João
                if mat == "T1001" and chave == "luva_vaqueta":
                    dias = 78                     # vida útil acaba em 12 dias: alerta
                if mat == "T1003" and chave == "capacete":
                    validade = 5                  # vence em 5 dias: alerta
                if mat == "T1007" and chave == "botina":
                    dias = 380                    # vida útil encerrada há 15 dias
                self._entregar(self._unidade(chave, validade), mat, dias)
        for chave in self.tp:
            if chave == "pff2":
                continue
            for _ in range(14):
                self._unidade(chave, self.rnd.randint(300, 1100))
        self._unidade("oculos", 25)               # estoque vencendo em 25 dias
        self._unidade("cinto", -15)               # vencido parado no estoque
        for _ in range(2):
            self._unidade("pff2", 400)            # modelo com CA vencido

    # ------------------------------------------------------------------ ocorrências
    # (matrícula -> [(tipo, motivo, dias atrás)]) — padrões que o gestor deve enxergar
    OCORRENCIAS = {
        "T1007": [("luva_vaqueta", "DANIFICADO", 160), ("capacete", "DANIFICADO", 120),
                  ("luva_vaqueta", "DANIFICADO", 85), ("oculos", "DANIFICADO", 64),
                  ("luva_vaqueta", "DANIFICADO", 41), ("protetor", "PERDA", 37)],
        "T1005": [("oculos", "DANIFICADO", 150), ("oculos", "DANIFICADO", 88),
                  ("botina", "DANIFICADO", 70), ("oculos", "DANIFICADO", 45)],
        "T1009": [("protetor", "PERDA", 140), ("oculos", "PERDA", 82),
                  ("protetor", "PERDA", 58), ("luva_vaqueta", "PERDA", 44),
                  ("capacete", "DANIFICADO", 36)],
        "T1003": [("luva_vaqueta", "DANIFICADO", 130), ("oculos", "PERDA", 75),
                  ("luva_vaqueta", "DANIFICADO", 52)],
        "T1010": [("protetor", "PERDA", 96), ("protetor", "PERDA", 47)],
        "T1006": [("oculos", "DANIFICADO", 66)],
        "T1008": [("protetor", "PERDA", 110)],
        "T1001": [("oculos", "DANIFICADO", 92)],
    }
    DESCRICOES = {
        "DANIFICADO": ["Rasgou na montagem", "Trincou ao cair", "Desgaste acima do normal",
                       "Queimado por respingo de solda", "Alça arrebentada"],
        "PERDA": ["Não encontrado após o turno", "Perdido no deslocamento",
                  "Esquecido em outra frente de trabalho e não localizado"],
    }

    def _ocorrencias(self):
        from reposicao.services import solicitar_reposicao
        eventos = [(dias, mat, chave, motivo)
                   for mat, lista in self.OCORRENCIAS.items() for chave, motivo, dias in lista]
        eventos.sort(key=lambda e: -e[0])  # do mais antigo para o mais recente
        for dias, mat, chave, motivo in eventos:
            trab = self.t[mat]
            entrega = EntregaEpi.objects.filter(trabalhador=trab, devolvido_em__isnull=True,
                                                unidade__tipo=self.tp[chave]).first()
            momento = self._momento(dias, self.rnd.randint(8, 16), self.rnd.randint(0, 59))
            if entrega is None or entrega.entregue_em >= momento:
                continue
            quem = self.usuario_de.get(mat, self.tecnico)
            with no_tempo(momento) as relogio:
                sol = solicitar_reposicao(
                    trabalhador=trab, tipo_epi=self.tp[chave], motivo=motivo, usuario=quem,
                    unidade=entrega.unidade, observacao=self.rnd.choice(self.DESCRICOES[motivo]))
                relogio.avancar(self.rnd.uniform(90, 1500))
                nova = UnidadeEpi.objects.filter(
                    tipo=self.tp[chave], status=UnidadeEpi.Status.ESTOQUE,
                    validade__gt=timezone.localdate() + timedelta(days=120)).first()
                if nova is None:
                    continue
                registrar_entrega(unidade=nova, trabalhador=trab, usuario=self.almox,
                                  assinatura_imagem=assinatura_svg(trab.nome), signatario_nome=trab.nome,
                                  motivo=EntregaEpi.Motivo.SUBSTITUICAO, solicitacao=sol,
                                  validar_assinatura=False)

    # ------------------------------------------------------------------ histórico
    def _concluir(self, pre, conferente, relogio):
        pre = PreLiberacao.objects.get(pk=pre.pk)
        sorteio = self.rnd.random()
        alvo = self.rnd.choice(list(pre.itens.all())) if sorteio < 0.11 else None
        problema = "AUSENTE" if sorteio < 0.08 else "DANIFICADO"
        obs = {"AUSENTE": "Esquecido no vestiário", "DANIFICADO": "Trinca visível na inspeção"}
        for item in pre.itens.all():
            relogio.avancar(self.rnd.uniform(0.2, 0.6))
            resultado = problema if item == alvo else "CONFORME"
            lib.marcar_item(item, usuario=conferente, resultado_fisico=resultado,
                            observacao=obs[problema] if item == alvo else "")
        nao = self.rnd.random() < 0.04
        for i, r in enumerate(pre.respostas.select_related("item_modelo")):
            relogio.avancar(self.rnd.uniform(0.1, 0.4))
            lib.responder_pergunta(r, usuario=conferente, valor=not (nao and i == 0))
        relogio.avancar(self.rnd.uniform(0.3, 1.0))
        return lib.concluir_conferencia(
            pre, usuario=conferente, assinatura_conferente=assinatura_svg(conferente.nome_exibicao),
            assinatura_colaborador=assinatura_svg(pre.trabalhador.nome),
            confirmou_fisico=True, validar_assinatura=False)

    def _historico(self):
        eventos = []
        for dias_atras in range(10, 0, -1):
            dia = self.hoje - timedelta(days=dias_atras)
            if dia.weekday() == 6:
                continue
            for mat in self.rnd.sample(list(self.t), k=self.rnd.randint(1, 2)):
                if mat == "T1001" and dias_atras <= 4:
                    continue  # preserva o talabarte vencido do João para o roteiro
                perfil = self.perfil_trab[mat]
                atividade = {"altura": self.rnd.choice([self.altura, self.altura, self.rotina]),
                             "eletrica": self.rnd.choice([self.eletrica, self.eletrica, self.rotina]),
                             "producao": self.rotina}[perfil]
                eventos.append((self._momento(dias_atras, self.rnd.randint(7, 15), self.rnd.randint(0, 59)),
                                mat, atividade))
        eventos.sort(key=lambda e: e[0])
        locais = {"altura": ["Torre de resfriamento 2", "Galpão de caldeiras, nível 3", "Fachada do prédio administrativo"],
                  "eletrica": ["Subestação 1, painel QGBT-02", "Sala elétrica da linha 3", "CCM da ETA"],
                  "producao": ["Linha de envase 1", "Linha de envase 2", "Expedição"]}
        motivos_bloqueio = ["Vento acima de 40 km/h na área de trabalho",
                             "PT sem assinatura do emitente da área",
                             "Equipe sem vigia designado para a tarefa"]
        limite_atendimento = _now_real() - timedelta(days=3)
        for momento, mat, atividade in eventos:
            trab = self.t[mat]
            solicitante = self.usuario_de.get(mat, self.tecnico)
            with no_tempo(momento) as relogio:
                pre = lib.abrir_pre_liberacao(
                    atividade=atividade, trabalhador=trab, usuario=solicitante,
                    local=self.rnd.choice(locais[self.perfil_trab[mat]]),
                    numero_pt_os=f"PT-2026-{self.rnd.randint(1000, 1999)}" if atividade.exige_aprovacao else "")
                relogio.avancar(self.rnd.uniform(1.5, 4.5))  # técnico chega ao local
                pre = self._concluir(pre, self.tecnico, relogio)
                if pre.status == PreLiberacao.Status.AGUARDANDO_APROVACAO:
                    relogio.avancar(self.rnd.uniform(1.5, 8))
                    liberar = self.rnd.random() > 0.08
                    lib.decidir(pre, usuario=self.gestor, liberar=liberar,
                                motivo="" if liberar else self.rnd.choice(motivos_bloqueio),
                                assinatura_imagem=assinatura_svg("Mariana Costa"),
                                signatario_nome="Mariana Costa", validar_assinatura=False)
                    pre.refresh_from_db()
                if pre.status == PreLiberacao.Status.BLOQUEADA and momento < limite_atendimento:
                    relogio.avancar(self.rnd.uniform(60, 600))
                    self._atender_reposicoes(trab)

    def _atender_reposicoes(self, trab):
        for sol in SolicitacaoReposicao.objects.filter(trabalhador=trab, status="ABERTA"):
            unidade = UnidadeEpi.objects.filter(
                tipo=sol.tipo_epi, status=UnidadeEpi.Status.ESTOQUE,
                validade__gt=timezone.localdate() + timedelta(days=60)).first()
            if unidade is None or not sol.tipo_epi.ca_vigente():
                continue
            registrar_entrega(unidade=unidade, trabalhador=trab, usuario=self.almox,
                              assinatura_imagem=assinatura_svg(trab.nome), signatario_nome=trab.nome,
                              motivo=EntregaEpi.Motivo.SUBSTITUICAO, solicitacao=sol,
                              validar_assinatura=False)

    # ------------------------------------------------------------------ cenário atual
    def _cenario_atual(self):
        agora = _now_real()
        tec = self.tecnico
        # Ana: NR-10 solicitada por ela, conferida pelo técnico, aguardando a gestora
        with no_tempo(agora - timedelta(minutes=14)) as relogio:
            pre = lib.abrir_pre_liberacao(
                atividade=self.eletrica, trabalhador=self.t["T1002"], usuario=self.ana,
                local="Subestação 1, painel QGBT-02", numero_pt_os="PT-2026-2087")
            relogio.avancar(4)
            for item in pre.itens.all():
                relogio.avancar(0.6)
                lib.marcar_item(item, usuario=tec, resultado_fisico="CONFORME")
            for r in pre.respostas.all():
                relogio.avancar(0.3)
                lib.responder_pergunta(r, usuario=tec, valor=True)
            relogio.avancar(1)
            lib.concluir_conferencia(pre, usuario=tec, assinatura_conferente=assinatura_svg("Rodrigo Teixeira"),
                                     assinatura_colaborador=assinatura_svg("Ana Souza"),
                                     confirmou_fisico=True, validar_assinatura=False)
        # Carlos: conferência em andamento, aberta pelo técnico no local
        with no_tempo(agora - timedelta(minutes=4)) as relogio:
            pre = lib.abrir_pre_liberacao(
                atividade=self.altura, trabalhador=self.t["T1003"], usuario=tec,
                local="Torre de resfriamento 2", numero_pt_os="PT-2026-2091")
            for item in list(pre.itens.all())[:2]:
                relogio.avancar(0.5)
                lib.marcar_item(item, usuario=tec, resultado_fisico="CONFORME")

        # Fernanda: ontem, luva isolante furada na conferência; atividade bloqueada e pedido aberto
        with no_tempo(timezone.make_aware(datetime.combine(self.hoje - timedelta(days=1), time(14, 20)))) as relogio:
            pre = lib.abrir_pre_liberacao(
                atividade=self.eletrica, trabalhador=self.t["T1004"], usuario=tec,
                local="Sala elétrica da linha 3", numero_pt_os="PT-2026-2079")
            for item in pre.itens.select_related("tipo_epi"):
                relogio.avancar(0.5)
                danificada = item.tipo_epi == self.tp["luva_isolante"]
                lib.marcar_item(item, usuario=tec,
                                resultado_fisico="DANIFICADO" if danificada else "CONFORME",
                                observacao="Furo no dedo indicador no teste de inflação" if danificada else "")
            for r in pre.respostas.all():
                lib.responder_pergunta(r, usuario=tec, valor=True)
            relogio.avancar(1)
            lib.concluir_conferencia(pre, usuario=tec, assinatura_conferente=assinatura_svg("Rodrigo Teixeira"),
                                     assinatura_colaborador=assinatura_svg("Fernanda Rocha"),
                                     confirmou_fisico=True, validar_assinatura=False)
        # Outros EPIs vencidos em uso, para a estatística "quem está fora da validade"
        for mat, chave, dias in (("T1005", "protetor", 12), ("T1010", "oculos", 4)):
            entrega = EntregaEpi.objects.filter(trabalhador=self.t[mat], devolvido_em__isnull=True,
                                                unidade__tipo=self.tp[chave]).select_related("unidade").first()
            if entrega:
                entrega.unidade.validade = self.hoje - timedelta(days=dias)
                entrega.unidade.save(update_fields=["validade"])
        # Lucas: avaria informada há 2 horas (registrada pelo técnico)
        from reposicao.services import solicitar_reposicao
        lucas = self.t["T1009"]
        oculos = EntregaEpi.objects.filter(trabalhador=lucas, devolvido_em__isnull=True,
                                           unidade__tipo=self.tp["oculos"]).first()
        if oculos:
            with no_tempo(agora - timedelta(hours=2)):
                solicitar_reposicao(trabalhador=lucas, tipo_epi=self.tp["oculos"], motivo="DANIFICADO",
                                    usuario=tec, unidade=oculos.unidade,
                                    observacao="Lente riscada, atrapalha a visão")

    def _resumo(self):
        self.stdout.write(self.style.SUCCESS(
            f"Dados de demonstração criados: {Trabalhador.objects.count()} trabalhadores, "
            f"{UnidadeEpi.objects.count()} unidades de EPI, "
            f"{PreLiberacao.objects.count()} pré-liberações."))
        self.stdout.write(f"Usuários (senha {SENHA}): operador, operador2, tecnico, gestor, almox, admin")

