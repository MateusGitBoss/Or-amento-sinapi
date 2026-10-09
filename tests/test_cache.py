from orcamento.cache import CacheMemoria, CachePostgres, chave_cache, versao_prompt
from orcamento.db import Conexao


def test_chave_muda_com_qualquer_parte() -> None:
    assert chave_cache("a", "b") != chave_cache("a", "c")
    assert chave_cache("ab", "c") != chave_cache("a", "bc")
    assert versao_prompt("x") != versao_prompt("y")


def test_cache_postgres(conn: Conexao) -> None:
    cache = CachePostgres(conn)
    assert cache.obter("k") is None
    cache.guardar("k", {"codigo": "1", "confianca": "alta"})
    cache.guardar("k", {"codigo": "2", "confianca": "alta"})
    assert cache.obter("k") == {"codigo": "2", "confianca": "alta"}


def test_cache_memoria_devolve_copia() -> None:
    cache = CacheMemoria()
    cache.guardar("k", {"a": [1]})
    copia = cache.obter("k")
    assert copia is not None
    copia["a"].append(2)
    assert cache.obter("k") == {"a": [1]}
