"""Conexão com o PostgreSQL e aplicação das migrações em ordem."""

import logging
from importlib import resources
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

Conexao = psycopg.Connection[dict[str, Any]]


def conectar(database_url: str) -> Conexao:
    return psycopg.connect(database_url, row_factory=dict_row)


def migrar(conn: Conexao) -> list[str]:
    """Aplica os arquivos de migrations/ que ainda não foram aplicados. Retorna os novos."""
    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                versao TEXT PRIMARY KEY,
                aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    aplicadas = {r["versao"] for r in conn.execute("SELECT versao FROM schema_migrations")}

    pasta = resources.files("orcamento") / "migrations"
    arquivos = sorted((p for p in pasta.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name)
    novas: list[str] = []
    for arquivo in arquivos:
        if arquivo.name in aplicadas:
            continue
        # Cada migração roda inteira ou não roda (transação)
        with conn.transaction():
            conn.execute(arquivo.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (versao) VALUES (%s)", (arquivo.name,))
        logger.info("migração aplicada", extra={"versao": arquivo.name})
        novas.append(arquivo.name)
    return novas
