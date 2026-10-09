from orcamento.db import Conexao, migrar


def test_migrar_e_idempotente(conn: Conexao) -> None:
    assert migrar(conn) == []
    tabelas = {
        r["tablename"]
        for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    assert {"insumos_sinapi", "importacoes", "cache_ia"} <= tabelas
