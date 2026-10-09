from pathlib import Path

import pytest
from typer.testing import CliRunner

from orcamento.cli import app
from orcamento.config import get_settings
from orcamento.db import Conexao

from .conftest import URL_TESTE

EXEMPLO = Path(__file__).parent.parent / "dados" / "exemplo" / "SINAPI_exemplo_MA_202608.xlsx"
runner = CliRunner()


@pytest.fixture
def ambiente(conn: Conexao, monkeypatch: pytest.MonkeyPatch) -> Conexao:
    monkeypatch.setenv("DATABASE_URL", URL_TESTE or "")
    monkeypatch.setenv("UF", "MA")
    get_settings.cache_clear()
    yield conn
    get_settings.cache_clear()


def test_migrar_importar_buscar(ambiente: Conexao) -> None:
    assert "já estava em dia" in runner.invoke(app, ["migrar"]).output

    importado = runner.invoke(app, ["importar", str(EXEMPLO), "--referencia", "2026-08"])
    assert importado.exit_code == 0, importado.output
    assert "61 insumos importados para MA 08/2026" in importado.output

    busca = runner.invoke(app, ["buscar", "tijolo 8 furos"])
    assert busca.exit_code == 0
    assert "7271" in busca.output


def test_referencia_invalida(ambiente: Conexao) -> None:
    resultado = runner.invoke(app, ["importar", str(EXEMPLO), "--referencia", "agosto"])
    assert resultado.exit_code != 0
    assert "AAAA-MM" in resultado.output


def test_buscar_sem_tabela(ambiente: Conexao) -> None:
    resultado = runner.invoke(app, ["buscar", "cimento"])
    assert resultado.exit_code == 1


def test_planilha_invalida(ambiente: Conexao, tmp_path: Path) -> None:
    ruim = tmp_path / "ruim.csv"
    ruim.write_text("a;b\n1;2\n", encoding="utf-8")
    resultado = runner.invoke(app, ["importar", str(ruim), "--referencia", "2026-08"])
    assert resultado.exit_code == 1
    assert "Planilha inválida" in resultado.output
