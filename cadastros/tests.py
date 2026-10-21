from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core import testutils as tu
from epis.models import UnidadeEpi

from .importacao import importar_trabalhadores, importar_unidades
from .models import Trabalhador


class ImportacaoTests(TestCase):
    def test_unidades_aceita_validas_e_rejeita_linhas_com_problema(self):
        tu.tipo("Capacete classe B", numero_ca="31469")
        tu.tipo("Óculos", numero_ca="11111", dias_ca=-5)
        csv = ("tipo;serie_lote;tamanho;fabricacao;validade\n"
               "Capacete classe B;L1;U;01/01/2026;31/12/2030\n"
               "31469;L2;U;;2031-06-30\n"
               "Capacete classe B;L3;U;;\n"
               "Bota inexistente;L4;42;;31/12/2030\n"
               "Óculos;L5;U;;31/12/2030\n"
               "Capacete classe B;L6;U;;01/01/2020\n").encode("cp1252")
        r = importar_unidades(SimpleUploadedFile("u.csv", csv))
        self.assertEqual(r["criados"], 2)
        self.assertEqual([n for n, _ in r["erros"]], [4, 5, 6, 7])
        self.assertEqual(UnidadeEpi.objects.count(), 2)

    def test_trabalhadores_atualiza_por_matricula(self):
        Trabalhador.objects.create(matricula="T1", nome="Antigo")
        csv = "matricula,nome,funcao,setor\nT1,Novo Nome,Soldador,Manutenção\nT2,Ana,,\n,Sem,,\n"
        r = importar_trabalhadores(SimpleUploadedFile("t.csv", csv.encode("utf-8")))
        self.assertEqual((r["criados"], r["atualizados"], len(r["erros"])), (1, 1, 1))
        self.assertEqual(Trabalhador.objects.get(matricula="T1").nome, "Novo Nome")
