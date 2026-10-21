"""Fábricas de dados para os testes automatizados."""
import base64
import struct
import zlib
from datetime import timedelta

from django.utils import timezone

from cadastros.models import Atividade, AtividadeEpiRequisito, ChecklistItemModelo, Trabalhador
from contas.models import Usuario
from epis.models import EntregaEpi, TipoEpi, UnidadeEpi


def png_dataurl(largura=120, altura=40):
    """PNG real com um traço, como o que o quadro de assinatura gera."""
    linhas = b""
    for y in range(altura):
        linha = bytearray([0])
        for x in range(largura):
            tinta = abs(y - (altura // 2 + int(8 * ((x % 30) / 30 - 0.5)))) < 2
            linha += bytes([20, 36, 48, 255]) if tinta else bytes([0, 0, 0, 0])
        linhas += bytes(linha)

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(
            ">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 6, 0, 0, 0))
           + bloco(b"IDAT", zlib.compress(linhas, 0))
           + bloco(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def hoje():
    return timezone.localdate()


def usuario(username, perfil, trabalhador=None, **extra):
    u = Usuario.objects.create_user(username=username, password="safeepi123", perfil=perfil,
                                     trabalhador=trabalhador, email=f"{username}@teste.local",
                                     **extra)
    return u


def tipo(nome="Capacete", dias_ca=400, vida_util=None, **extra):
    return TipoEpi.objects.create(
        nome=nome, categoria=extra.pop("categoria", "CABECA"),
        numero_ca=extra.pop("numero_ca", str(10000 + TipoEpi.objects.count())),
        validade_ca=hoje() + timedelta(days=dias_ca), vida_util_dias=vida_util, **extra)


def unidade(tipo_epi, dias_validade=300, status=UnidadeEpi.Status.ESTOQUE, **extra):
    return UnidadeEpi.objects.create(
        tipo=tipo_epi, validade=hoje() + timedelta(days=dias_validade) if dias_validade is not None else None,
        status=status, **extra)


def entregar(u, trabalhador, por, dias_atras=10):
    """Entrega direta (sem regras), para montar cenários — inclusive com EPI vencido."""
    u.status = UnidadeEpi.Status.ENTREGUE
    u.save()
    return EntregaEpi.objects.create(unidade=u, trabalhador=trabalhador, entregue_por=por,
                                     entregue_em=timezone.now() - timedelta(days=dias_atras))


def cenario(exige_aprovacao=True, perguntas=1):
    """Trabalhador com usuário, gestor, almoxarife e atividade com 2 EPIs entregues e válidos."""
    t = Trabalhador.objects.create(matricula="T001", nome="João Pereira")
    op = usuario("op", Usuario.Perfil.OPERACIONAL, trabalhador=t)
    gestor = usuario("gestor", Usuario.Perfil.GESTOR_SST, first_name="Mariana")
    tecnico = usuario("tecnico", Usuario.Perfil.TECNICO_SST, first_name="Rodrigo")
    almox = usuario("almox", Usuario.Perfil.ALMOX)
    capacete = tipo("Capacete")
    luva = tipo("Luva", categoria="MAOS")
    atividade = Atividade.objects.create(nome="Trabalho em altura", nr_referencia="NR-35",
                                         exige_aprovacao=exige_aprovacao)
    AtividadeEpiRequisito.objects.create(atividade=atividade, tipo_epi=capacete)
    AtividadeEpiRequisito.objects.create(atividade=atividade, tipo_epi=luva)
    for i in range(perguntas):
        ChecklistItemModelo.objects.create(atividade=atividade, texto=f"PT emitida {i}?", ordem=i)
    u_cap = unidade(capacete)
    u_luva = unidade(luva)
    entregar(u_cap, t, almox)
    entregar(u_luva, t, almox)
    return {"t": t, "op": op, "gestor": gestor, "tecnico": tecnico, "almox": almox, "capacete": capacete,
            "luva": luva, "atividade": atividade, "u_cap": u_cap, "u_luva": u_luva}
