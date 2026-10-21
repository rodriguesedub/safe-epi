from django import forms

from cadastros.models import Trabalhador

from .models import EntregaEpi, TipoEpi, UnidadeEpi, hoje


class EntregaForm(forms.Form):
    trabalhador = forms.ModelChoiceField(
        queryset=Trabalhador.objects.filter(ativo=True), label="Trabalhador")
    tipo = forms.ModelChoiceField(
        queryset=TipoEpi.objects.all(), label="Tipo de EPI", required=False,
        help_text="Filtra as unidades disponíveis.")
    unidade = forms.ModelChoiceField(queryset=UnidadeEpi.objects.none(), label="Unidade a entregar")
    motivo = forms.ChoiceField(choices=EntregaEpi.Motivo.choices, label="Motivo")
    observacao = forms.CharField(label="Observação", required=False, max_length=200)
    signatario_nome = forms.CharField(label="Nome de quem assina", max_length=120)
    assinatura = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = unidades_disponiveis(tipo)

    def clean_assinatura(self):
        valor = self.cleaned_data.get("assinatura", "")
        if not valor:
            raise forms.ValidationError("O trabalhador precisa assinar no quadro.")
        return valor


def unidades_disponiveis(tipo=None):
    qs = UnidadeEpi.objects.filter(status=UnidadeEpi.Status.ESTOQUE).select_related("tipo")
    qs = qs.exclude(validade__lt=hoje()).exclude(tipo__validade_ca__lt=hoje())
    if tipo:
        qs = qs.filter(tipo=tipo)
    return qs.order_by("tipo__nome", "validade", "codigo")
