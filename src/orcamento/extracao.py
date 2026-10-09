"""Extração: transforma "10 sacos cimento cp2" em {quantidade: 10, unidade: SC, descricao: ...}.

Dois extratores com a mesma interface:
- por regra (expressão regular): grátis, previsível, entende só o formato "número unidade coisa";
- por IA: entende abreviação e apelido de obra, custa uma chamada (com cache).
O conjunto de avaliação compara os dois.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import anthropic
from pydantic import ValidationError

from orcamento.cache import Cache, chave_cache, versao_prompt
from orcamento.ia import chamar_json, ler_prompt
from orcamento.modelos import UNIDADES, ItemExtraido
from orcamento.texto import normalizar

log = logging.getLogger(__name__)


SINONIMOS_UNIDADE = {
    "un": "UN", "und": "UN", "unid": "UN", "unidade": "UN", "unidades": "UN",
    "pc": "PC", "pca": "PC", "peca": "PC", "pecas": "PC", "barra": "PC", "barras": "PC",
    "kg": "KG", "quilo": "KG", "quilos": "KG",
    "t": "T", "ton": "T", "tonelada": "T", "toneladas": "T",
    "m": "M", "metro": "M", "metros": "M", "ml": "M",
    "m2": "M2", "m²": "M2",
    "m3": "M3", "m³": "M3",
    "l": "L", "litro": "L", "litros": "L", "lt": "L",
    "sc": "SC", "saco": "SC", "sacos": "SC",
    "mil": "MIL", "milheiro": "MIL", "milheiros": "MIL",
    "h": "H", "hora": "H", "horas": "H", "hr": "H",
}  # fmt: skip

_PADRAO = re.compile(r"^\s*(?P<qtd>\d+(?:[.,]\d+)*)\s*(?P<resto>.*)$")


def _numero(texto: str) -> Decimal | None:
    """'2,5' = 2.5; '1.000' = mil (ponto como milhar, costume brasileiro); '1.5' = 1.5."""
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


class Extrator(Protocol):
    def extrair(self, linha: str) -> ItemExtraido | None: ...


class ExtratorRegra:
    """Entende "<número> [unidade] [de] <material>". Qualquer outra coisa devolve None."""

    def extrair(self, linha: str) -> ItemExtraido | None:
        achou = _PADRAO.match(normalizar(linha).replace("²", "2").replace("³", "3"))
        if not achou:
            return None
        quantidade = _numero(achou["qtd"])
        palavras = achou["resto"].split()
        unidade = None
        if palavras and palavras[0] in SINONIMOS_UNIDADE:
            unidade = SINONIMOS_UNIDADE[palavras.pop(0)]
        if palavras and palavras[0] == "de":
            palavras.pop(0)
        descricao = " ".join(palavras)
        if quantidade is None or quantidade <= 0 or len(descricao) < 2:
            return None
        return ItemExtraido(quantidade=quantidade, unidade=unidade, descricao=descricao)


ESQUEMA_EXTRACAO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "quantidade": {"type": "number"},
        "unidade": {"anyOf": [{"type": "string", "enum": list(UNIDADES)}, {"type": "null"}]},
        "descricao": {"type": "string"},
    },
    "required": ["quantidade", "unidade", "descricao"],
    "additionalProperties": False,
}


class ExtratorIA:
    def __init__(
        self, cliente: anthropic.Anthropic, modelo: str, cache: Cache, prompt: str | None = None
    ) -> None:
        self.cliente = cliente
        self.modelo = modelo
        self.cache = cache
        self.prompt = prompt if prompt is not None else ler_prompt("extracao.md")
        self.versao = versao_prompt(self.prompt)

    def extrair(self, linha: str) -> ItemExtraido | None:
        entrada = normalizar(linha)
        chave = chave_cache("extracao", self.modelo, self.versao, entrada)
        dados = self.cache.obter(chave)
        if dados is None:
            dados = chamar_json(
                self.cliente,
                self.modelo,
                self.prompt,
                f"<linha>{entrada}</linha>",
                ESQUEMA_EXTRACAO,
            )
            if dados is None:
                return None
            self.cache.guardar(chave, dados)
        try:
            # Pydantic valida o que a IA devolveu: quantidade > 0, descrição não vazia
            return ItemExtraido.model_validate(dados)
        except ValidationError:
            log.warning("extração da IA fora do formato", extra={"linha": linha, "dados": dados})
            return None
