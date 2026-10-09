"""Cache das respostas da IA no Postgres.

A chave junta tipo da chamada, modelo, versão do prompt e entrada. Mudou o prompt, muda a
versão e a chave: o cache antigo deixa de valer sozinho, sem ninguém precisar limpar.
"""

import hashlib
import json
from typing import Any, Protocol

from psycopg.types.json import Jsonb

from orcamento.db import Conexao


def chave_cache(*partes: str) -> str:
    return hashlib.sha256("\x1f".join(partes).encode()).hexdigest()


def versao_prompt(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()[:12]


class Cache(Protocol):
    def obter(self, chave: str) -> dict[str, Any] | None: ...

    def guardar(self, chave: str, valor: dict[str, Any]) -> None: ...


class CachePostgres:
    def __init__(self, conn: Conexao) -> None:
        self.conn = conn

    def obter(self, chave: str) -> dict[str, Any] | None:
        linha = self.conn.execute(
            "SELECT resposta FROM cache_ia WHERE chave = %s", (chave,)
        ).fetchone()
        return dict(linha["resposta"]) if linha else None

    def guardar(self, chave: str, valor: dict[str, Any]) -> None:
        with self.conn.transaction():
            self.conn.execute(
                """
                INSERT INTO cache_ia (chave, resposta) VALUES (%s, %s)
                ON CONFLICT (chave) DO UPDATE SET resposta = EXCLUDED.resposta, criado_em = now()
                """,
                (chave, Jsonb(valor)),
            )


class CacheMemoria:
    """Usado nos testes e quando não se quer gravar nada."""

    def __init__(self) -> None:
        self.dados: dict[str, dict[str, Any]] = {}

    def obter(self, chave: str) -> dict[str, Any] | None:
        valor = self.dados.get(chave)
        return json.loads(json.dumps(valor)) if valor is not None else None

    def guardar(self, chave: str, valor: dict[str, Any]) -> None:
        self.dados[chave] = valor
