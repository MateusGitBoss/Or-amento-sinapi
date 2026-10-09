"""Fixtures compartilhadas. Testes de banco usam DATABASE_URL_TESTE (no CI, service container)."""

import os
from collections.abc import Iterator

import pytest

from orcamento.db import Conexao, conectar, migrar

URL_TESTE = os.environ.get("DATABASE_URL_TESTE")


@pytest.fixture
def conn() -> Iterator[Conexao]:
    if not URL_TESTE:
        pytest.skip("DATABASE_URL_TESTE não definida")
    with conectar(URL_TESTE) as conexao:
        conexao.execute(
            "DROP TABLE IF EXISTS insumos_sinapi, importacoes, cache_ia, schema_migrations"
        )
        conexao.commit()
        migrar(conexao)
        yield conexao
