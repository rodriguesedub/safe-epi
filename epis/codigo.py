"""Código de identificação do EPI (decisão D4).

Formato: EPI-000123-7, onde 7 é o dígito verificador (algoritmo de Luhn).
A mesma string será o conteúdo do QR Code na fase 2; o dígito
verificador pega erros de digitação no MVP.
"""
import re

_PADRAO = re.compile(r"^EPI-?(\d{6})-?(\d)$")


def digito_luhn(numero: str) -> int:
    soma = 0
    for i, c in enumerate(reversed(numero)):
        d = int(c)
        if i % 2 == 0:  # posições que serão dobradas (a contar do DV)
            d *= 2
            if d > 9:
                d -= 9
        soma += d
    return (10 - soma % 10) % 10


def gerar_codigo(sequencial: int) -> str:
    base = f"{sequencial:06d}"
    return f"EPI-{base}-{digito_luhn(base)}"


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", "", (texto or "").upper())


def codigo_valido(texto: str) -> bool:
    m = _PADRAO.match(normalizar(texto))
    return bool(m) and digito_luhn(m.group(1)) == int(m.group(2))


def canonico(texto: str) -> str:
    """Devolve o código no formato com hífens, ou o texto normalizado se inválido."""
    t = normalizar(texto)
    m = _PADRAO.match(t)
    if not m:
        return t
    return f"EPI-{m.group(1)}-{m.group(2)}"
