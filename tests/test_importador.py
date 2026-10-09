from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from orcamento.db import Conexao
from orcamento.importador import (
    ErroPlanilha,
    importar,
    ler_planilha,
    preco_para_centavos,
    ultima_referencia,
)

EXEMPLO = Path(__file__).parent.parent / "dados" / "exemplo" / "SINAPI_exemplo_MA_202608.xlsx"
AGOSTO = date(2026, 8, 1)


def planilha(tmp_path: Path, linhas: list[list[object]], nome: str = "p.xlsx") -> Path:
    wb = Workbook()
    aba = wb.active
    assert aba is not None
    for linha in linhas:
        aba.append(linha)
    caminho = tmp_path / nome
    wb.save(caminho)
    return caminho


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (38.9, 3890),
        ("38,90", 3890),
        ("1.450,00", 145000),
        ("R$ 0,78", 78),
        (1450, 145000),
        ("", None),
        ("abc", None),
        ("-1,00", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_preco_para_centavos(valor: object, esperado: int | None) -> None:
    assert preco_para_centavos(valor) == esperado


def test_le_planilha_de_exemplo() -> None:
    insumos, descartadas = ler_planilha(EXEMPLO)
    assert len(insumos) == 61
    assert descartadas == 0
    cimento = insumos[insumos["codigo"] == "1379"].iloc[0]
    assert cimento["descricao"] == "CIMENTO PORTLAND COMPOSTO CP II-32"
    assert cimento["unidade"] == "KG"
    assert cimento["preco_centavos"] == 78
    assert cimento["descricao_busca"] == "cimento portland composto cp ii-32"


def test_acha_cabecalho_em_qualquer_linha_e_descarta_lixo(tmp_path: Path) -> None:
    caminho = planilha(
        tmp_path,
        [
            ["Título qualquer"],
            [],
            ["Código", "Descrição do Insumo", "Unidade", "Preço Mediano R$"],
            ["00001379", "CIMENTO", "kg ", "0,78"],
            [1379, "CIMENTO DUPLICADO", "KG", "0,99"],  # código repetido: fica o primeiro
            [None, "SEM CÓDIGO", "KG", "1,00"],
            [7271, "BLOCO", "MIL", "sem preço"],
            ["Fonte: Caixa", None, None, None],
        ],
    )
    insumos, descartadas = ler_planilha(caminho)
    assert insumos["codigo"].tolist() == ["1379"]
    assert insumos["unidade"].tolist() == ["KG"]
    assert descartadas == 4


def test_le_csv(tmp_path: Path) -> None:
    caminho = tmp_path / "p.csv"
    caminho.write_text("CODIGO;DESCRICAO;UNIDADE;PRECO\n33;ACO CA-50;KG;8,45\n", encoding="utf-8")
    insumos, _ = ler_planilha(caminho)
    assert insumos.iloc[0]["preco_centavos"] == 845


def test_sem_cabecalho(tmp_path: Path) -> None:
    with pytest.raises(ErroPlanilha, match="cabeçalho"):
        ler_planilha(planilha(tmp_path, [["a", "b"], [1, 2]]))


def test_sem_coluna_de_preco(tmp_path: Path) -> None:
    with pytest.raises(ErroPlanilha, match="preco"):
        ler_planilha(planilha(tmp_path, [["CODIGO", "DESCRICAO", "UNIDADE"], [1, "x", "KG"]]))


def test_importar_e_idempotente_por_mes(conn: Conexao) -> None:
    primeiro = importar(conn, EXEMPLO, "MA", date(2026, 8, 15))
    segundo = importar(conn, EXEMPLO, "MA", AGOSTO)

    assert primeiro.referencia == AGOSTO  # qualquer dia vira dia 1
    assert primeiro.linhas == segundo.linhas == 61
    total = conn.execute("SELECT count(*) AS n FROM insumos_sinapi").fetchone()
    assert total == {"n": 61}
    assert conn.execute("SELECT count(*) AS n FROM importacoes").fetchone() == {"n": 1}


def test_meses_diferentes_convivem(conn: Conexao) -> None:
    importar(conn, EXEMPLO, "MA", AGOSTO)
    importar(conn, EXEMPLO, "MA", date(2026, 9, 1))
    assert ultima_referencia(conn, "MA") == date(2026, 9, 1)
    assert ultima_referencia(conn, "PI") is None


def test_planilha_vazia_nao_apaga_o_mes(conn: Conexao, tmp_path: Path) -> None:
    importar(conn, EXEMPLO, "MA", AGOSTO)
    vazia = planilha(tmp_path, [["CODIGO", "DESCRICAO", "UNIDADE", "PRECO"]])
    with pytest.raises(ErroPlanilha, match="nenhum insumo"):
        importar(conn, vazia, "MA", AGOSTO)
    assert conn.execute("SELECT count(*) AS n FROM insumos_sinapi").fetchone() == {"n": 61}
