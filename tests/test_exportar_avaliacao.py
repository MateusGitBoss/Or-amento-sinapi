import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from orcamento.avaliacao import CasoAvaliacao, ResultadoCaso, avaliar, carregar_conjunto
from orcamento.exportar import exportar
from orcamento.orcamento import LinhaOrcamento, Orcamento

CONJUNTO = Path(__file__).parent.parent / "dados" / "avaliacao" / "conjunto.csv"

ORCAMENTO = Orcamento(
    uf="MA",
    referencia=date(2026, 8, 1),
    itens=[
        LinhaOrcamento(
            linha="1500 tijolo 8 furos",
            quantidade=Decimal(1500),
            codigo="7271",
            descricao="BLOCO CERAMICO 8 FUROS",
            unidade="MIL",
            quantidade_sinapi=Decimal("1.5"),
            preco_unitario_centavos=78000,
            subtotal_centavos=117000,
            confianca="alta",
            revisar=False,
        ),
        LinhaOrcamento(linha="6 parafuso", motivo="busca não achou candidatos"),
    ],
)


def test_exporta_csv(tmp_path: Path) -> None:
    destino = tmp_path / "o.csv"
    exportar(ORCAMENTO, destino)
    linhas = list(csv.reader(destino.open(encoding="utf-8-sig"), delimiter=";"))
    assert linhas[1][:3] == ["OK", "1500 tijolo 8 furos", "7271"]
    assert linhas[1][5:8] == ["1,50", "780", "1170"]
    assert linhas[2][0] == "REVISAR"
    assert linhas[4][0] == "TOTAL (itens OK)" and linhas[4][7] == "1170"


def test_exporta_xlsx(tmp_path: Path) -> None:
    destino = tmp_path / "o.xlsx"
    exportar(ORCAMENTO, destino)
    aba = load_workbook(destino).active
    assert aba is not None
    assert aba["A1"].value == "Orçamento - SINAPI MA 08/2026"
    assert aba["C4"].value == "7271"
    assert float(aba["H4"].value) == 1170.0
    assert aba["A5"].value == "REVISAR"
    assert aba["H5"].value is None  # item em revisão não tem subtotal na planilha
    assert float(aba["H7"].value) == 1170.0


def test_formato_desconhecido(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        exportar(ORCAMENTO, tmp_path / "o.pdf")


def test_conjunto_de_avaliacao_tem_30_linhas() -> None:
    casos = carregar_conjunto(CONJUNTO)
    assert len(casos) == 30
    assert casos[-1].codigo_esperado is None  # item sem correspondência no SINAPI


@pytest.mark.parametrize(
    ("esperado", "codigo", "revisar", "tipo"),
    [
        ("1", "1", False, "acerto"),
        ("1", "2", False, "erro_calado"),
        ("1", "2", True, "revisao"),
        ("1", "1", True, "revisao"),
        (None, None, True, "acerto"),
        (None, "3", False, "erro_calado"),
    ],
)
def test_classificacao(esperado: str | None, codigo: str | None, revisar: bool, tipo: str) -> None:
    resultado = ResultadoCaso(
        CasoAvaliacao("x", esperado), LinhaOrcamento(linha="x", codigo=codigo, revisar=revisar)
    )
    assert resultado.tipo == tipo


def test_relatorio() -> None:
    class Falso:
        def orcar_linha(self, linha: str) -> LinhaOrcamento:
            return LinhaOrcamento(linha=linha, codigo=linha, revisar=linha == "b")

    casos = [CasoAvaliacao("a", "a"), CasoAvaliacao("b", "b"), CasoAvaliacao("c", "x")]
    relatorio = avaliar(Falso(), casos)  # type: ignore[arg-type]
    assert (relatorio.acertos, relatorio.revisoes, relatorio.erros_calados) == (1, 1, 1)
    assert round(relatorio.percentual(relatorio.acertos)) == 33
