from decimal import Decimal

import anthropic
import httpx2
import pytest

from orcamento.cache import CacheMemoria
from orcamento.extracao import ExtratorIA, ExtratorRegra
from orcamento.ia import ErroIA

from .fakes import ClienteFalso, mensagem


@pytest.mark.parametrize(
    ("linha", "quantidade", "unidade", "descricao"),
    [
        ("10 sacos cimento cp2", "10", "SC", "cimento cp2"),
        ("3 m3 de areia média", "3", "M3", "areia media"),
        ("2m³ areia fina", "2", "M3", "areia fina"),
        ("2,5 kg arame", "2.5", "KG", "arame"),
        ("1500 tijolo 8 furos", "1500", None, "tijolo 8 furos"),
        ("40 horas servente", "40", "H", "servente"),
        ("1.000 m fio", "1000", "M", "fio"),
    ],
)
def test_regra(linha: str, quantidade: str, unidade: str | None, descricao: str) -> None:
    item = ExtratorRegra().extrair(linha)
    assert item is not None
    assert (item.quantidade, item.unidade, item.descricao) == (
        Decimal(quantidade),
        unidade,
        descricao,
    )


@pytest.mark.parametrize("linha", ["cimento", "0 sacos cimento", "10 sacos", "", "12"])
def test_regra_nao_entende(linha: str) -> None:
    assert ExtratorRegra().extrair(linha) is None


def extrator(cliente: ClienteFalso, cache: CacheMemoria | None = None) -> ExtratorIA:
    return ExtratorIA(
        cliente.como_anthropic(), "claude-haiku-5-5", cache or CacheMemoria(), "PROMPT"
    )


def test_ia_extrai_e_usa_cache() -> None:
    cliente = ClienteFalso(
        mensagem(
            {"quantidade": 10, "unidade": "SC", "descricao": "cimento portland composto cp ii-32"}
        )
    )
    ia = extrator(cliente)

    primeira = ia.extrair("10 sacos cimento cp2")
    segunda = ia.extrair("10  Sacos  CIMENTO cp2")  # mesma linha normalizada

    assert primeira == segunda
    assert primeira is not None and primeira.unidade == "SC"
    assert len(cliente.chamadas) == 1
    chamada = cliente.chamadas[0]
    assert chamada["system"] == "PROMPT"
    assert chamada["messages"][0]["content"] == "<linha>10 sacos cimento cp2</linha>"
    assert chamada["output_config"]["format"]["type"] == "json_schema"


def test_mudar_o_prompt_invalida_o_cache() -> None:
    cache = CacheMemoria()
    dados = {"quantidade": 1, "unidade": None, "descricao": "areia"}
    cliente = ClienteFalso(mensagem(dados), mensagem(dados))
    ExtratorIA(cliente.como_anthropic(), "m", cache, "PROMPT v1").extrair("areia")
    ExtratorIA(cliente.como_anthropic(), "m", cache, "PROMPT v2").extrair("areia")
    assert len(cliente.chamadas) == 2


def test_ia_fora_do_formato_vira_none_e_nao_vai_para_o_cache() -> None:
    cache = CacheMemoria()
    cliente = ClienteFalso(mensagem({"quantidade": -3, "unidade": "SC", "descricao": "cimento"}))
    assert extrator(cliente, cache).extrair("x cimento") is None


@pytest.mark.parametrize(
    "resposta", [mensagem("{", "max_tokens"), mensagem("nada", "refusal"), mensagem("[1]")]
)
def test_resposta_inaproveitavel(resposta: object) -> None:
    cache = CacheMemoria()
    assert extrator(ClienteFalso(resposta), cache).extrair("10 sacos cimento") is None  # type: ignore[arg-type]
    assert cache.dados == {}


def test_erro_de_rede() -> None:
    erro = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
    with pytest.raises(ErroIA):
        extrator(ClienteFalso(erro)).extrair("10 sacos cimento")


def test_prompt_padrao_vem_do_pacote() -> None:
    ia = ExtratorIA(ClienteFalso().como_anthropic(), "m", CacheMemoria())
    assert "SINAPI" in ia.prompt
    assert "Não informe preço" in ia.prompt
