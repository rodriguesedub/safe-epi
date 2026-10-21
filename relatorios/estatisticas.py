"""Estatísticas de EPI para o gestor de SST.

Responde às perguntas do professor: quantos EPIs existem de cada tipo, quem mais
danifica, quem mais perde e quem está usando EPI fora da validade.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from cadastros.models import Trabalhador
from epis.models import EntregaEpi, TipoEpi, UnidadeEpi, hoje
from epis.services import avaliar_unidade
from liberacoes.models import ConferenciaItem
from reposicao.models import SolicitacaoReposicao

U = UnidadeEpi.Status
PERIODOS = [(30, "30 dias"), (90, "90 dias"), (180, "6 meses")]


def _ranking(contador, limite=6):
    """[(nome, valor, pct_da_barra)] ordenado do maior para o menor."""
    itens = [(nome, n) for nome, n in contador.most_common() if n > 0][:limite]
    maior = max([n for _, n in itens] or [1])
    return [{"nome": nome, "valor": n, "pct": round(100 * n / maior)} for nome, n in itens]


def estatisticas(dias=90):
    data = hoje()
    desde = timezone.now() - timedelta(days=dias)
    limite_30 = data + timedelta(days=30)

    # ---------------------------------------------- estoque por tipo ("quanto tem de cada")
    por_tipo = defaultdict(Counter)
    vencidas_por_tipo = Counter()
    vencendo_por_tipo = Counter()
    for u in UnidadeEpi.objects.select_related("tipo"):
        por_tipo[u.tipo_id][u.status] += 1
        if u.status in (U.ESTOQUE, U.ENTREGUE) and u.validade:
            if u.validade < data:
                vencidas_por_tipo[u.tipo_id] += 1
            elif u.validade <= limite_30:
                vencendo_por_tipo[u.tipo_id] += 1

    repos = SolicitacaoReposicao.objects.filter(criada_em__gte=desde).select_related(
        "trabalhador", "tipo_epi")
    danos_tipo, perdas_tipo = Counter(), Counter()
    danos_trab, perdas_trab = Counter(), Counter()
    for r in repos:
        if r.motivo == SolicitacaoReposicao.Motivo.DANIFICADO:
            danos_tipo[r.tipo_epi_id] += 1
            danos_trab[r.trabalhador_id] += 1
        elif r.motivo == SolicitacaoReposicao.Motivo.PERDA:
            perdas_tipo[r.tipo_epi_id] += 1
            perdas_trab[r.trabalhador_id] += 1

    ausencias_trab = Counter(
        ConferenciaItem.objects.filter(
            resultado_fisico=ConferenciaItem.Fisico.AUSENTE,
            pre_liberacao__aberta_em__gte=desde,
        ).values_list("pre_liberacao__trabalhador_id", flat=True)
    )

    estoque = []
    for t in TipoEpi.objects.order_by("nome"):
        c = por_tipo.get(t.pk, Counter())
        fora = c[U.AVARIADO] + c[U.EXTRAVIADO] + c[U.DESCARTADO]
        estoque.append({
            "tipo": t,
            "estoque": c[U.ESTOQUE],
            "em_uso": c[U.ENTREGUE],
            "fora_de_uso": fora,
            "total": sum(c.values()),
            "vencidas": vencidas_por_tipo[t.pk],
            "vencendo": vencendo_por_tipo[t.pk],
            "danos": danos_tipo[t.pk],
            "perdas": perdas_tipo[t.pk],
            "ca_vencido": not t.ca_vigente(data),
        })

    # ---------------------------------------------- quem está com EPI fora da validade
    fora_validade = []
    vencidos_trab = Counter()
    for e in EntregaEpi.objects.filter(devolvido_em__isnull=True).select_related(
            "unidade__tipo", "trabalhador"):
        resultado, motivo = avaliar_unidade(e.unidade, e, data)
        if resultado in ("VENCIDO", "CA_VENCIDO"):
            vencidos_trab[e.trabalhador_id] += 1
            fora_validade.append({"entrega": e, "motivo": motivo, "resultado": resultado})
    fora_validade.sort(key=lambda x: x["entrega"].trabalhador.nome)

    # ---------------------------------------------- ocorrências por colaborador
    nomes = dict(Trabalhador.objects.values_list("pk", "nome"))
    ocorrencias = []
    for pk in set(danos_trab) | set(perdas_trab) | set(ausencias_trab) | set(vencidos_trab):
        linha = {
            "trabalhador_id": pk, "nome": nomes.get(pk, "?"),
            "danos": danos_trab[pk], "perdas": perdas_trab[pk],
            "ausencias": ausencias_trab[pk], "vencidos": vencidos_trab[pk],
        }
        linha["total"] = linha["danos"] + linha["perdas"] + linha["ausencias"] + linha["vencidos"]
        ocorrencias.append(linha)
    ocorrencias.sort(key=lambda x: (-x["total"], x["nome"]))

    tot = Counter()
    for c in por_tipo.values():
        tot.update(c)
    return {
        "dias": dias,
        "periodos": PERIODOS,
        "kpis": {
            "em_uso": tot[U.ENTREGUE],
            "estoque": tot[U.ESTOQUE],
            "fora_de_uso": tot[U.AVARIADO] + tot[U.EXTRAVIADO] + tot[U.DESCARTADO],
            "avariados": tot[U.AVARIADO] + tot[U.DESCARTADO],
            "extraviados": tot[U.EXTRAVIADO],
            "vencidos_em_uso": len(fora_validade),
            "colaboradores_vencidos": len(vencidos_trab),
            "danos": sum(danos_trab.values()),
            "perdas": sum(perdas_trab.values()),
        },
        "estoque": estoque,
        "mais_danifica": _ranking(Counter({nomes[k]: v for k, v in danos_trab.items()})),
        "mais_perde": _ranking(Counter({nomes[k]: v for k, v in perdas_trab.items()})),
        "fora_validade": fora_validade,
        "ocorrencias": ocorrencias,
    }
