"""Escolha: entre os candidatos da busca, qual é o insumo certo (ou nenhum)."""

import json
import logging
from typing import Any, Protocol

import anthropic
from pydantic import ValidationError

from orcamento.busca import Candidato
from orcamento.cache import Cache, chave_cache, versao_prompt
from orcamento.ia import chamar_json, ler_prompt
from orcamento.modelos import Escolha, ItemExtraido
from orcamento.texto import normalizar

log = logging.getLogger(__name__)


class Escolhedor(Protocol):
    def escolher(self, linha: str, item: ItemExtraido, candidatos: list[Candidato]) -> Escolha: ...


class EscolhaRegra:
    """Fica com o primeiro da busca. A confiança vem da nota e da distância para o segundo.

    Limiares calibrados olhando a busca na planilha de exemplo; num catálogo maior eles
    precisariam ser recalibrados com o conjunto de avaliação.
    """

    def __init__(self, nota_alta: float = 0.45, nota_minima: float = 0.15, margem: float = 0.05):
        self.nota_alta = nota_alta
        self.nota_minima = nota_minima
        self.margem = margem

    def escolher(self, linha: str, item: ItemExtraido, candidatos: list[Candidato]) -> Escolha:
        if not candidatos:
            return Escolha(codigo=None, confianca="baixa", motivo="busca não achou candidatos")
        primeiro = candidatos[0]
        distancia = primeiro.nota - (candidatos[1].nota if len(candidatos) > 1 else 0.0)
        if primeiro.nota >= self.nota_alta and distancia >= 2 * self.margem:
            confianca = "alta"
        elif primeiro.nota >= self.nota_minima and distancia >= self.margem:
            confianca = "media"
        else:
            confianca = "baixa"
        return Escolha(
            codigo=primeiro.codigo,
            confianca=confianca,
            motivo=f"maior nota da busca ({primeiro.nota:.2f}, {distancia:.2f} acima do segundo)",
        )


ESQUEMA_ESCOLHA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "codigo": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
        "motivo": {"type": "string"},
    },
    "required": ["codigo", "confianca", "motivo"],
    "additionalProperties": False,
}


def montar_conteudo(linha: str, item: ItemExtraido, candidatos: list[Candidato]) -> str:
    lista = "\n".join(
        f'<candidato codigo="{c.codigo}" unidade="{c.unidade}">{c.descricao}</candidato>'
        for c in candidatos
    )
    unidade = item.unidade or "não informada"
    return (
        f"<linha>{normalizar(linha)}</linha>\n"
        f"<item>quantidade={item.quantidade}; unidade={unidade}; material={item.descricao}</item>\n"
        f"<candidatos>\n{lista}\n</candidatos>"
    )


class EscolhaIA:
    def __init__(
        self, cliente: anthropic.Anthropic, modelo: str, cache: Cache, prompt: str | None = None
    ) -> None:
        self.cliente = cliente
        self.modelo = modelo
        self.cache = cache
        self.prompt = prompt if prompt is not None else ler_prompt("escolha.md")
        self.versao = versao_prompt(self.prompt)

    def escolher(self, linha: str, item: ItemExtraido, candidatos: list[Candidato]) -> Escolha:
        if not candidatos:
            return Escolha(codigo=None, confianca="baixa", motivo="busca não achou candidatos")
        conteudo = montar_conteudo(linha, item, candidatos)
        # A chave inclui os candidatos: tabela de outro mês pode trazer outros códigos
        chave = chave_cache("escolha", self.modelo, self.versao, conteudo)
        dados = self.cache.obter(chave)
        if dados is None:
            dados = chamar_json(self.cliente, self.modelo, self.prompt, conteudo, ESQUEMA_ESCOLHA)
            if dados is None:
                return Escolha(codigo=None, confianca="baixa", motivo="IA não respondeu no formato")
            self.cache.guardar(chave, dados)
        try:
            escolha = Escolha.model_validate(dados)
        except ValidationError:
            log.warning("escolha da IA fora do formato", extra={"dados": json.dumps(dados)})
            return Escolha(codigo=None, confianca="baixa", motivo="IA respondeu fora do formato")

        # A IA só pode escolher entre os candidatos: código inventado é descartado
        if escolha.codigo is not None and escolha.codigo not in {c.codigo for c in candidatos}:
            log.warning("IA devolveu código fora dos candidatos", extra={"codigo": escolha.codigo})
            return Escolha(codigo=None, confianca="baixa", motivo="IA indicou código fora da lista")
        if escolha.codigo is None:
            return escolha.model_copy(update={"confianca": "baixa"})
        return escolha
