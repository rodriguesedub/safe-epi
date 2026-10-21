"""Alertas de vencimento de EPI, CA e vida útil (RF13)."""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from auditoria.services import auditar
from epis.models import EntregaEpi, TipoEpi, UnidadeEpi, hoje

from .models import Alerta

A = Alerta


def faixas():
    return sorted(settings.SAFEEPI.get("ALERTA_DIAS", [30, 15, 7]))


def faixa_de(vence_em, data):
    dias = (vence_em - data).days
    if dias < 0:
        return 0
    for f in faixas():
        if dias <= f:
            return f
    return None


@transaction.atomic
def gerar_alertas(data=None, enviar_email=True, usuario=None, request=None):
    data = data or hoje()
    horizonte = data + timedelta(days=max(faixas()))
    desejados = {}  # (tipo, unidade_id, tipo_epi_id) -> vence_em

    ativos = [UnidadeEpi.Status.ESTOQUE, UnidadeEpi.Status.ENTREGUE]
    for u in UnidadeEpi.objects.filter(status__in=ativos, validade__lte=horizonte):
        desejados[(A.Tipo.VALIDADE_EPI, u.pk, None)] = u.validade

    for e in EntregaEpi.objects.filter(devolvido_em__isnull=True,
                                       unidade__tipo__vida_util_dias__isnull=False
                                       ).select_related("unidade__tipo"):
        fim = e.fim_vida_util
        if fim and fim <= horizonte:
            desejados[(A.Tipo.VIDA_UTIL, e.unidade_id, None)] = fim

    for t in TipoEpi.objects.filter(validade_ca__lte=horizonte, unidades__status__in=ativos).distinct():
        desejados[(A.Tipo.VALIDADE_CA, None, t.pk)] = t.validade_ca

    abertos = {(a.tipo, a.unidade_id, a.tipo_epi_id): a
               for a in Alerta.objects.filter(status=A.Status.ABERTO)}
    criados = atualizados = resolvidos = 0
    for chave, vence_em in desejados.items():
        faixa = faixa_de(vence_em, data)
        if faixa is None:
            continue
        alerta = abertos.pop(chave, None)
        if alerta is None:
            Alerta.objects.create(tipo=chave[0], unidade_id=chave[1], tipo_epi_id=chave[2],
                                  vence_em=vence_em, dias_antecedencia=faixa,
                                  gerado_em=timezone.now())
            criados += 1
        elif alerta.vence_em != vence_em or alerta.dias_antecedencia != faixa:
            alerta.vence_em, alerta.dias_antecedencia = vence_em, faixa
            alerta.save(update_fields=["vence_em", "dias_antecedencia"])
            atualizados += 1
    agora = timezone.now()
    for alerta in abertos.values():  # condição deixou de existir
        alerta.status, alerta.resolvido_em = A.Status.RESOLVIDO, agora
        alerta.save(update_fields=["status", "resolvido_em"])
        resolvidos += 1

    total_abertos = Alerta.objects.filter(status=A.Status.ABERTO).count()
    enviado = False
    if enviar_email and total_abertos:
        enviado = _enviar_resumo(data)
    resumo = {"criados": criados, "atualizados": atualizados, "resolvidos": resolvidos,
              "abertos": total_abertos, "email_enviado": enviado}
    auditar("alertas.verificados", usuario=usuario, request=request,
            descricao=f"{criados} novos, {resolvidos} resolvidos, {total_abertos} abertos",
            depois=resumo)
    return resumo


def resolver_alertas_da_unidade(unidade):
    Alerta.objects.filter(unidade=unidade, status=A.Status.ABERTO).update(
        status=A.Status.RESOLVIDO, resolvido_em=timezone.now()
    )


def _enviar_resumo(data):
    from contas.models import Usuario
    destinatarios = list(
        Usuario.objects.filter(
            is_active=True,
            perfil__in=[Usuario.Perfil.GESTOR_SST, Usuario.Perfil.ALMOX],
        ).exclude(email="").values_list("email", flat=True)
    )
    if not destinatarios:
        return False
    alertas = Alerta.objects.filter(status=A.Status.ABERTO).select_related("unidade__tipo", "tipo_epi")
    linhas = []
    for a in alertas[:30]:
        alvo = f"{a.unidade.codigo} {a.unidade.tipo.nome}" if a.unidade_id else f"Modelo {a.tipo_epi.nome}"
        linhas.append(f"- {a.vence_em:%d/%m/%Y} | {a.get_tipo_display()} | {alvo} | {a.faixa_label}")
    vencidos = alertas.filter(dias_antecedencia=0).count()
    corpo = (
        f"Resumo de vencimentos em {data:%d/%m/%Y}\n\n"
        f"{alertas.count()} alertas abertos, dos quais {vencidos} já vencidos.\n\n"
        + "\n".join(linhas)
        + "\n\nAbra o painel de alertas do SAFEEPI para ver todos."
    )
    send_mail(f"SAFEEPI: {alertas.count()} alertas de vencimento", corpo,
              None, destinatarios, fail_silently=True)
    return True
