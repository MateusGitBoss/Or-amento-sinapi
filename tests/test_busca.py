from datetime import date
from pathlib import Path

import pytest

from orcamento.busca import buscar_candidatos, obter_insumo
from orcamento.db import Conexao
from orcamento.importador import importar

EXEMPLO = Path(__file__).parent.parent / "dados" / "exemplo" / "SINAPI_exemplo_MA_202608.xlsx"
AGOSTO = date(2026, 8, 1)


@pytest.fixture
def base(conn: Conexao) -> Conexao:
    importar(conn, EXEMPLO, "MA", AGOSTO)
    return conn


@pytest.mark.parametrize(
    ("texto", "codigo_esperado"),
    [
        ("tijolo 8 furos", "7271"),
        ("bloco ceramico 8 furos", "7271"),
        ("cimento cp ii 32 saco 50kg", "1381"),
        ("areia media", "370"),
        ("brita 1", "4721"),
        ("vergalhão 10mm ca 50", "34"),
        ("arame recozido", "337"),
        ("tinta latex acrilica branca", "7356"),
        ("tubo pvc esgoto 100mm", "9838"),
        ("cabo flexivel 2,5mm", "1014"),
        ("cimeto portland", "1379"),  # erro de digitação: só trigrama salva
    ],
)
def test_candidato_certo_entre_os_5(base: Conexao, texto: str, codigo_esperado: str) -> None:
    candidatos = buscar_candidatos(base, texto, "MA", AGOSTO)
    assert codigo_esperado in [c.codigo for c in candidatos], [
        (c.codigo, c.descricao, round(c.nota, 3)) for c in candidatos
    ]


def test_ordena_pela_nota(base: Conexao) -> None:
    notas = [c.nota for c in buscar_candidatos(base, "cimento portland", "MA", AGOSTO)]
    assert notas == sorted(notas, reverse=True)


def test_respeita_uf_e_mes(base: Conexao) -> None:
    assert buscar_candidatos(base, "cimento", "PI", AGOSTO) == []
    assert buscar_candidatos(base, "cimento", "MA", date(2026, 7, 1)) == []


def test_texto_vazio(base: Conexao) -> None:
    assert buscar_candidatos(base, "  ", "MA", AGOSTO) == []


def test_obter_insumo(base: Conexao) -> None:
    insumo = obter_insumo(base, "7271", "MA", AGOSTO)
    assert insumo is not None and insumo.preco_centavos == 78000
    assert obter_insumo(base, "999999", "MA", AGOSTO) is None
