"""Importação de planilhas CSV (RF20): migra o que hoje está em papel e Excel."""
import csv
import io
from datetime import datetime

from django.db import transaction

from auditoria.services import auditar
from epis.models import TipoEpi, UnidadeEpi, hoje

from .models import Trabalhador


class _PontoEVirgula(csv.excel):
    delimiter = ";"


def _ler(arquivo):
    bruto = arquivo.read()
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    amostra = texto[:2000]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,")
    except csv.Error:
        dialeto = _PontoEVirgula
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    leitor.fieldnames = [(c or "").strip().lower() for c in (leitor.fieldnames or [])]
    return leitor


def _data(valor):
    valor = (valor or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    return None


@transaction.atomic
def importar_trabalhadores(arquivo, usuario=None, request=None):
    leitor = _ler(arquivo)
    faltando = {"matricula", "nome"} - set(leitor.fieldnames)
    if faltando:
        return {"criados": 0, "atualizados": 0,
                "erros": [(1, f"Colunas obrigatórias ausentes: {', '.join(sorted(faltando))}")]}
    criados = atualizados = 0
    erros = []
    for n, linha in enumerate(leitor, start=2):
        matricula = (linha.get("matricula") or "").strip()
        nome = (linha.get("nome") or "").strip()
        if not matricula or not nome:
            erros.append((n, "Matrícula e nome são obrigatórios."))
            continue
        _, criado = Trabalhador.objects.update_or_create(
            matricula=matricula,
            defaults={"nome": nome, "funcao": (linha.get("funcao") or "").strip(),
                      "setor": (linha.get("setor") or "").strip(), "ativo": True},
        )
        criados += criado
        atualizados += not criado
    auditar("importacao.trabalhadores", usuario=usuario, request=request,
            descricao=f"{criados} criados, {atualizados} atualizados, {len(erros)} linhas rejeitadas")
    return {"criados": criados, "atualizados": atualizados, "erros": erros}


@transaction.atomic
def importar_unidades(arquivo, usuario=None, request=None):
    leitor = _ler(arquivo)
    faltando = {"tipo", "validade"} - set(leitor.fieldnames)
    if faltando:
        return {"criados": 0, "atualizados": 0,
                "erros": [(1, f"Colunas obrigatórias ausentes: {', '.join(sorted(faltando))}")]}
    tipos_nome = {t.nome.lower(): t for t in TipoEpi.objects.all()}
    tipos_ca = {t.numero_ca: t for t in TipoEpi.objects.all()}
    criados = 0
    erros = []
    for n, linha in enumerate(leitor, start=2):
        chave = (linha.get("tipo") or "").strip()
        tipo = tipos_nome.get(chave.lower()) or tipos_ca.get(chave)
        if tipo is None:
            erros.append((n, f"Tipo de EPI \"{chave}\" não cadastrado (use o nome exato ou o nº do CA)."))
            continue
        validade = _data(linha.get("validade"))
        if validade is None:
            erros.append((n, "Validade vazia ou em formato inválido (use dd/mm/aaaa)."))
            continue
        if validade < hoje():
            erros.append((n, f"Validade {validade:%d/%m/%Y} já passou."))
            continue
        if not tipo.ca_vigente():
            erros.append((n, f"CA {tipo.numero_ca} de {tipo.nome} está vencido."))
            continue
        UnidadeEpi.objects.create(
            tipo=tipo, validade=validade, fabricacao=_data(linha.get("fabricacao")),
            serie_lote=(linha.get("serie_lote") or "").strip()[:40],
            tamanho=(linha.get("tamanho") or "").strip()[:10],
        )
        criados += 1
    auditar("importacao.unidades", usuario=usuario, request=request,
            descricao=f"{criados} unidades criadas, {len(erros)} linhas rejeitadas")
    return {"criados": criados, "atualizados": 0, "erros": erros}
