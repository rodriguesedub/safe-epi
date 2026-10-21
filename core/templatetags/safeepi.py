from datetime import date, timedelta

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_FORMAS = {
    # Formas da sinalização de segurança: quadrado verde = condição segura,
    # triângulo amarelo = atenção, círculo vermelho barrado = proibido,
    # círculo azul = ação obrigatória (falta conferir).
    "ok": '<rect x="2" y="2" width="20" height="20" rx="2.5" fill="#1F7A4D"/>'
          '<path d="M7 12.4l3.3 3.3L17.2 8.8" stroke="#fff" stroke-width="2.6" fill="none" '
          'stroke-linecap="round" stroke-linejoin="round"/>',
    "atencao": '<path d="M12 2.6L22.6 20.6H1.4Z" fill="#F2B705" stroke="#1C2430" '
               'stroke-width="1.6" stroke-linejoin="round"/>'
               '<rect x="10.9" y="8.4" width="2.2" height="6.6" rx="1.1" fill="#1C2430"/>'
               '<circle cx="12" cy="17.7" r="1.3" fill="#1C2430"/>',
    "bloqueio": '<circle cx="12" cy="12" r="9.3" fill="#fff" stroke="#A8261D" stroke-width="3"/>'
                '<path d="M5.5 5.5L18.5 18.5" stroke="#A8261D" stroke-width="3"/>',
    "conferir": '<circle cx="12" cy="12" r="10.5" fill="#134B8A"/>'
                '<circle cx="12" cy="12" r="4.6" fill="none" stroke="#fff" stroke-width="2.4"/>',
    "neutro": '<circle cx="12" cy="12" r="9.5" fill="none" stroke="#7A8492" stroke-width="2"/>'
              '<path d="M7.5 12h9" stroke="#7A8492" stroke-width="2.2"/>',
}


@register.simple_tag
def sinal(chave, tamanho="sm", rotulo=""):
    forma = _FORMAS.get(chave, _FORMAS["neutro"])
    aria = format_html('role="img" aria-label="{}"', rotulo) if rotulo else 'aria-hidden="true"'
    return mark_safe(
        f'<svg class="sinal sinal-{tamanho}" viewBox="0 0 24 24" {aria} '
        f'focusable="false">{forma}</svg>'
    )


@register.filter
def sinal_pre(status):
    return {
        "LIBERADA": "ok", "BLOQUEADA": "bloqueio", "AGUARDANDO_APROVACAO": "atencao",
        "EM_CONFERENCIA": "conferir", "CANCELADA": "neutro",
    }.get(status, "neutro")


@register.filter
def sinal_item(item):
    if not item.auto_ok:
        return "bloqueio"
    if item.resultado_fisico == "CONFORME":
        return "ok"
    if item.resultado_fisico == "PENDENTE":
        return "conferir"
    return "bloqueio"


@register.filter
def sinal_alerta(alerta):
    return "bloqueio" if alerta.dias_antecedencia == 0 else "atencao"


@register.filter
def duracao(td):
    if td is None:
        return "—"
    if not isinstance(td, timedelta):
        return td
    minutos = int(td.total_seconds() // 60)
    if minutos < 1:
        return "menos de 1 min"
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 48:
        return f"{horas} h {resto:02d} min"
    return f"{horas // 24} dias"


@register.filter
def minutos(valor):
    if valor is None:
        return "—"
    if valor < 1:
        return "< 1"
    return f"{valor:.0f}" if valor >= 10 else f"{valor:.1f}".replace(".", ",")


@register.filter
def pct(valor):
    if valor is None:
        return "—"
    return f"{valor:.0f}%"


@register.simple_tag(takes_context=True)
def url_ativa(context, url):
    path = context["request"].path
    if url == "/":
        return "atual" if path == "/" else ""
    return "atual" if path.startswith(url) else ""


@register.simple_tag
def ca(obj, validade=None):
    """Certificado de Aprovação do EPI, em todas as telas: {% ca tipo %} ou {% ca "41201" data %}."""
    if obj is None or obj == "":
        return ""
    if hasattr(obj, "numero_ca"):
        numero, validade = obj.numero_ca, obj.validade_ca
    else:
        numero = obj
    if isinstance(validade, str):
        try:
            validade = date.fromisoformat(validade)
        except ValueError:
            validade = None
    vencido = bool(validade and validade < timezone.localdate())
    if validade:
        titulo = (f"Certificado de Aprovação nº {numero}, "
                  + (f"vencido em {validade:%d/%m/%Y}" if vencido else f"válido até {validade:%d/%m/%Y}"))
    else:
        titulo = f"Certificado de Aprovação nº {numero}"
    return format_html(
        '<span class="ca{}" title="{}">CA {}{}</span>',
        " ca-vencido" if vencido else "", titulo, numero, " vencido" if vencido else "",
    )


@register.filter
def iniciais(nome):
    partes = [p for p in (nome or "").split() if p[:1].isalpha()]
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()
