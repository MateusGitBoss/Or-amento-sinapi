from decimal import Decimal

from orcamento.busca import Candidato
from orcamento.cache import CacheMemoria
from orcamento.escolha import EscolhaIA, EscolhaRegra, montar_conteudo
from orcamento.modelos import ItemExtraido

from .fakes import ClienteFalso, mensagem

ITEM = ItemExtraido(quantidade=Decimal(15), unidade="UN", descricao="luva pvc soldavel 25 mm")
CANDIDATOS = [
    Candidato("9868", "TUBO PVC, SOLDAVEL, DN 25 MM", "M", 420, 0.18),
    Candidato("3540", "JOELHO PVC, SOLDAVEL, 90 GRAUS, 25 MM", "UN", 95, 0.16),
]


def test_regra_confianca_pela_nota_e_distancia() -> None:
    regra = EscolhaRegra()
    alta = [Candidato("1", "a", "UN", 1, 0.6), Candidato("2", "b", "UN", 1, 0.3)]
    media = [Candidato("1", "a", "UN", 1, 0.2), Candidato("2", "b", "UN", 1, 0.1)]
    baixa = CANDIDATOS  # 0,18 contra 0,16: empate técnico
    assert regra.escolher("", ITEM, alta).confianca == "alta"
    assert regra.escolher("", ITEM, media).confianca == "media"
    escolha = regra.escolher("", ITEM, baixa)
    assert (escolha.codigo, escolha.confianca) == ("9868", "baixa")
    assert regra.escolher("", ITEM, [Candidato("1", "a", "UN", 1, 0.5)]).confianca == "alta"


def test_regra_sem_candidatos() -> None:
    assert EscolhaRegra().escolher("", ITEM, []).codigo is None


def escolha_ia(*respostas: object) -> tuple[EscolhaIA, ClienteFalso]:
    cliente = ClienteFalso(*respostas)  # type: ignore[arg-type]
    return EscolhaIA(cliente.como_anthropic(), "m", CacheMemoria(), "PROMPT"), cliente


def test_conteudo_lista_candidatos_com_unidade() -> None:
    conteudo = montar_conteudo("15 luva pvc 25", ITEM, CANDIDATOS)
    assert "<linha>15 luva pvc 25</linha>" in conteudo
    assert '<candidato codigo="3540" unidade="UN">JOELHO PVC' in conteudo
    assert "unidade=UN" in conteudo


def test_ia_recusa_material_parecido() -> None:
    ia, _ = escolha_ia(
        mensagem({"codigo": None, "confianca": "media", "motivo": "luva não é tubo"})
    )
    escolha = ia.escolher("15 luva pvc 25", ITEM, CANDIDATOS)
    # Sem código, a confiança é sempre baixa: o item vai para revisão
    assert (escolha.codigo, escolha.confianca) == (None, "baixa")


def test_ia_escolhe_e_usa_cache() -> None:
    resposta = {"codigo": "3540", "confianca": "alta", "motivo": "joelho 25 mm"}
    ia, cliente = escolha_ia(mensagem(resposta))
    assert ia.escolher("15 joelho 25", ITEM, CANDIDATOS).codigo == "3540"
    assert ia.escolher("15 joelho 25", ITEM, CANDIDATOS).codigo == "3540"
    assert len(cliente.chamadas) == 1


def test_codigo_inventado_e_descartado() -> None:
    ia, _ = escolha_ia(mensagem({"codigo": "99999", "confianca": "alta", "motivo": "x"}))
    escolha = ia.escolher("15 luva", ITEM, CANDIDATOS)
    assert (escolha.codigo, escolha.confianca) == (None, "baixa")
    assert "fora da lista" in escolha.motivo


def test_resposta_inaproveitavel() -> None:
    ia, _ = escolha_ia(mensagem("{", "max_tokens"))
    assert ia.escolher("15 luva", ITEM, CANDIDATOS).codigo is None


def test_resposta_fora_do_formato() -> None:
    ia, _ = escolha_ia(mensagem({"codigo": "3540", "confianca": "talvez", "motivo": ""}))
    assert ia.escolher("15 luva", ITEM, CANDIDATOS).codigo is None


def test_sem_candidatos_nem_chama_a_ia() -> None:
    ia, cliente = escolha_ia()
    assert ia.escolher("x", ITEM, []).codigo is None
    assert cliente.chamadas == []
