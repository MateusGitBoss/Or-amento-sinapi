from datetime import date
from decimal import Decimal

import pytest

from orcamento.busca import Candidato
from orcamento.modelos import Escolha, ItemExtraido
from orcamento.orcamento import Orcamentista, calcular_subtotal, converter

TIJOLO = Candidato("7271", "BLOCO CERAMICO 8 FUROS", "MIL", 78000, 0.5)
CIMENTO_KG = Candidato("1379", "CIMENTO CP II-32", "KG", 78, 0.5)


class ExtratorFixo:
    def __init__(self, itens: dict[str, ItemExtraido | None]) -> None:
        self.itens = itens

    def extrair(self, linha: str) -> ItemExtraido | None:
        return self.itens[linha]


class EscolhaFixa:
    def __init__(self, escolha: Escolha) -> None:
        self.escolha = escolha

    def escolher(self, linha: str, item: ItemExtraido, candidatos: list[Candidato]) -> Escolha:
        return self.escolha


def orcamentista(
    item: ItemExtraido | None, candidatos: list[Candidato], escolha: Escolha
) -> Orcamentista:
    return Orcamentista(
        ExtratorFixo({"linha": item}),
        EscolhaFixa(escolha),
        lambda texto: candidatos,
        "MA",
        date(2026, 8, 1),
    )


@pytest.mark.parametrize(
    ("qtd", "de", "para", "esperado"),
    [
        ("1500", "UN", "MIL", "1.5"),
        ("2", "MIL", "UN", "2000"),
        ("3", "M3", "M3", "3"),
        ("120", None, "UN", "120"),
        ("1500", None, "MIL", "1.5"),
    ],
)
def test_converter(qtd: str, de: str | None, para: str, esperado: str) -> None:
    convertida, _ = converter(Decimal(qtd), de, para)
    assert convertida == Decimal(esperado)


def test_saco_para_kg_nao_converte_sozinho() -> None:
    convertida, motivo = converter(Decimal(10), "SC", "KG")
    assert convertida is None
    assert "depende do produto" in motivo


def test_subtotal_arredonda_meio_centavo_para_cima() -> None:
    assert calcular_subtotal(Decimal("1.5"), 78000) == 117000
    assert calcular_subtotal(Decimal("0.5"), 1) == 1


def test_item_aprovado_com_preco_do_banco() -> None:
    item = ItemExtraido(quantidade=Decimal(1500), unidade=None, descricao="tijolo 8 furos")
    linha = orcamentista(item, [TIJOLO], Escolha(codigo="7271", confianca="alta")).orcar_linha(
        "linha"
    )
    assert not linha.revisar
    assert linha.quantidade_sinapi == Decimal("1.5")
    assert linha.preco_unitario_centavos == 78000
    assert linha.subtotal_centavos == 117000
    assert "contada como UN" in linha.motivo


@pytest.mark.parametrize(
    ("item", "candidatos", "escolha", "motivo"),
    [
        (None, [], Escolha(codigo=None, confianca="baixa"), "não entendi"),
        (
            ItemExtraido(quantidade=Decimal(1), descricao="xx"),
            [TIJOLO],
            Escolha(codigo=None, confianca="baixa", motivo="nenhum serve"),
            "nenhum serve",
        ),
        (
            ItemExtraido(quantidade=Decimal(10), unidade="SC", descricao="cimento"),
            [CIMENTO_KG],
            Escolha(codigo="1379", confianca="alta"),
            "depende do produto",
        ),
        (
            ItemExtraido(quantidade=Decimal(1), unidade="MIL", descricao="tijolo"),
            [TIJOLO],
            Escolha(codigo="7271", confianca="baixa", motivo="dúvida"),
            "dúvida",
        ),
    ],
)
def test_vai_para_revisao(
    item: ItemExtraido | None, candidatos: list[Candidato], escolha: Escolha, motivo: str
) -> None:
    linha = orcamentista(item, candidatos, escolha).orcar_linha("linha")
    assert linha.revisar
    assert motivo in linha.motivo


def test_total_ignora_itens_em_revisao_e_linhas_vazias() -> None:
    itens = {
        "1 milheiro tijolo": ItemExtraido(quantidade=Decimal(1), unidade="MIL", descricao="tijolo"),
        "10 sacos cimento": ItemExtraido(quantidade=Decimal(10), unidade="SC", descricao="cimento"),
    }
    candidatos = {"tijolo": [TIJOLO], "cimento": [CIMENTO_KG]}
    escolhas = {"tijolo": "7271", "cimento": "1379"}

    class EscolhaPorItem:
        def escolher(self, linha: str, item: ItemExtraido, c: list[Candidato]) -> Escolha:
            return Escolha(codigo=escolhas[item.descricao], confianca="alta")

    o = Orcamentista(
        ExtratorFixo(itens), EscolhaPorItem(), lambda t: candidatos[t], "MA", date(2026, 8, 1)
    ).orcar(["1 milheiro tijolo", "", "# comentário", "10 sacos cimento"])

    assert len(o.itens) == 2
    assert o.total_centavos == 78000
    assert [i.linha for i in o.para_revisar] == ["10 sacos cimento"]
