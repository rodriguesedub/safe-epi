"""Indicadores do MVP (seção 11 da especificação)."""
from collections import Counter
from datetime import timedelta
from statistics import median

from django.utils import timezone

from alertas.models import Alerta
from epis.models import UnidadeEpi
from liberacoes.models import ConferenciaItem, PreLiberacao
from reposicao.models import SolicitacaoReposicao

S = PreLiberacao.Status


def _mediana_min(pres):
    tempos = [(p.decidida_em - p.aberta_em).total_seconds() / 60 for p in pres if p.decidida_em]
    return median(tempos) if tempos else None


def kpis(dias=30):
    desde = timezone.now() - timedelta(days=dias)
    periodo = PreLiberacao.objects.filter(aberta_em__gte=desde)
    decididas = list(periodo.filter(status__in=[S.LIBERADA, S.BLOQUEADA]))
    liberadas = [p for p in decididas if p.status == S.LIBERADA]
    bloqueadas = [p for p in decididas if p.status == S.BLOQUEADA]
    canceladas = periodo.filter(status=S.CANCELADA).count()
    finalizadas = len(decididas) + canceladas

    t_aprov = _mediana_min([p for p in liberadas if p.exige_aprovacao])
    t_reg = _mediana_min([p for p in liberadas if not p.exige_aprovacao])

    # K4: nenhuma liberação com EPI vencido, com CA vencido ou não entregue
    liberadas_com_problema = ConferenciaItem.objects.filter(
        pre_liberacao__status=S.LIBERADA, pre_liberacao__aberta_em__gte=desde,
    ).exclude(resultado_auto=ConferenciaItem.Auto.OK).values("pre_liberacao").distinct().count()
    barrados = ConferenciaItem.objects.filter(
        pre_liberacao__status=S.BLOQUEADA, pre_liberacao__aberta_em__gte=desde,
    ).exclude(resultado_auto=ConferenciaItem.Auto.OK).count()

    # K5: alertas emitidos com pelo menos 15 dias de antecedência
    alertas = list(Alerta.objects.filter(gerado_em__gte=desde))
    com_antecedencia = [a for a in alertas
                        if (a.vence_em - timezone.localtime(a.gerado_em).date()).days >= 15]
    pct_antecedencia = 100 * len(com_antecedencia) / len(alertas) if alertas else None

    # K6: cobertura de dados mestres
    ativas = UnidadeEpi.objects.filter(status__in=[UnidadeEpi.Status.ESTOQUE, UnidadeEpi.Status.ENTREGUE])
    total_ativas = ativas.count()
    completas = ativas.exclude(validade__isnull=True).exclude(tipo__numero_ca="").count()

    # K7: atendimento de reposição
    atendidas = SolicitacaoReposicao.objects.filter(
        status=SolicitacaoReposicao.Status.ATENDIDA, atendida_em__gte=desde)
    horas = [(s.atendida_em - s.criada_em).total_seconds() / 3600 for s in atendidas]

    motivos = Counter()
    for p in bloqueadas:
        for item in (p.snapshot or {}).get("itens", []):
            if item.get("resultado_auto") != "OK":
                motivos[{"VENCIDO": "EPI vencido", "CA_VENCIDO": "CA vencido",
                         "AVARIADO": "EPI avariado", "NAO_ENTREGUE": "EPI não entregue"}
                        .get(item["resultado_auto"], item["resultado_auto"])] += 1
            elif item.get("resultado_fisico") in ("AUSENTE", "DANIFICADO", "VENCIDO"):
                motivos[{"AUSENTE": "Ausente na conferência", "DANIFICADO": "Danificado na conferência",
                         "VENCIDO": "Vencido na conferência"}[item["resultado_fisico"]]] += 1
        for r in (p.snapshot or {}).get("checklist", []):
            if r.get("bloqueante") and r.get("resposta") is False:
                motivos["Checklist respondido com Não"] += 1

    hoje = timezone.localdate()
    vencidos_em_uso = UnidadeEpi.objects.filter(status=UnidadeEpi.Status.ENTREGUE,
                                                validade__lt=hoje).count()
    return {
        "dias": dias,
        "t_aprovacao": t_aprov,
        "t_registro": t_reg,
        "n_decididas": len(decididas),
        "n_liberadas": len(liberadas),
        "n_bloqueadas": len(bloqueadas),
        "pct_bloqueio": 100 * len(bloqueadas) / len(decididas) if decididas else None,
        "taxa_conclusao": 100 * len(decididas) / finalizadas if finalizadas else None,
        "liberadas_com_problema": liberadas_com_problema,
        "barrados": barrados,
        "pct_antecedencia": pct_antecedencia,
        "cobertura": 100 * completas / total_ativas if total_ativas else None,
        "reposicao_horas": median(horas) if horas else None,
        "reposicoes_abertas": SolicitacaoReposicao.objects.filter(
            status=SolicitacaoReposicao.Status.ABERTA).count(),
        "aguardando": PreLiberacao.objects.filter(status=S.AGUARDANDO_APROVACAO).count(),
        "em_conferencia": PreLiberacao.objects.filter(status=S.EM_CONFERENCIA).count(),
        "vencidos_em_uso": vencidos_em_uso,
        "alertas_abertos": Alerta.objects.filter(status=Alerta.Status.ABERTO).count(),
        "alertas_vencidos": Alerta.objects.filter(status=Alerta.Status.ABERTO, dias_antecedencia=0).count(),
        "motivos": motivos.most_common(6),
    }


def indicadores(k):
    """Tabela K1–K10 com valor atual, meta e situação (ok / atencao / neutro)."""
    def sit(cond):
        return "neutro" if cond is None else ("ok" if cond else "atencao")

    def fmt_min(v):
        return "sem dados" if v is None else (f"{v:.1f} min".replace(".", ",") if v < 10 else f"{v:.0f} min")

    def fmt_pct(v):
        return "sem dados" if v is None else f"{v:.0f}%"

    return [
        ("K1", "Tempo de pré-liberação (modo aprovação)",
         fmt_min(k["t_aprovacao"]), "≤ 10 min",
         sit(None if k["t_aprovacao"] is None else k["t_aprovacao"] <= 10)),
        ("K1", "Tempo de pré-liberação (modo registro)",
         fmt_min(k["t_registro"]), "≤ 5 min",
         sit(None if k["t_registro"] is None else k["t_registro"] <= 5)),
        ("K2", "Pré-liberações abertas que chegam a decisão",
         fmt_pct(k["taxa_conclusao"]), "≥ 90%",
         sit(None if k["taxa_conclusao"] is None else k["taxa_conclusao"] >= 90)),
        ("K3", "Tempo para montar o histórico de um trabalhador",
         "Medir no teste", "≤ 1 min", "neutro"),
        ("K4", "Liberações com EPI vencido, CA vencido ou não entregue",
         str(k["liberadas_com_problema"]), "0", sit(k["liberadas_com_problema"] == 0)),
        ("K5", "Alertas emitidos com 15 dias ou mais de antecedência",
         fmt_pct(k["pct_antecedencia"]), "≥ 95%",
         sit(None if k["pct_antecedencia"] is None else k["pct_antecedencia"] >= 95)),
        ("K6", "Unidades ativas com validade e CA cadastrados",
         fmt_pct(k["cobertura"]), "100%",
         sit(None if k["cobertura"] is None else k["cobertura"] >= 99.5)),
        ("K7", "Tempo mediano de atendimento de reposição",
         "sem dados" if k["reposicao_horas"] is None else f"{k['reposicao_horas']:.0f} h",
         "Linha de base", "neutro"),
        ("K8", "Usabilidade (questionário SUS)", "Aplicar no teste", "≥ 70", "neutro"),
        ("K9", "Conclusão da pré-liberação sem ajuda", "Aplicar no teste", "≥ 80%", "neutro"),
        ("K10", "Custo de infraestrutura", "R$ 0 (local)", "R$ 0", "ok"),
    ]
