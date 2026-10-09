"""Chamada ao Claude com saída em JSON garantida por esquema (structured outputs)."""

import json
import logging
from importlib import resources
from typing import Any

import anthropic

log = logging.getLogger(__name__)


def ler_prompt(nome: str) -> str:
    """Prompts ficam versionados em src/orcamento/prompts/: mudam por PR, com revisão."""
    return (resources.files("orcamento") / "prompts" / nome).read_text(encoding="utf-8")


class ErroIA(Exception):
    """Falha de rede/API. Não é a IA dizendo "não sei": é a chamada que não aconteceu."""


def chamar_json(
    cliente: anthropic.Anthropic,
    modelo: str,
    sistema: str,
    conteudo: str,
    esquema: dict[str, Any],
    max_tokens: int = 1024,
) -> dict[str, Any] | None:
    """Devolve o JSON da resposta, ou None quando a resposta não é aproveitável.

    None cobre recusa do filtro de segurança, JSON cortado por max_tokens e JSON inválido.
    Quem chama trata None como "precisa revisão humana".
    """
    try:
        resposta = cliente.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=sistema,
            messages=[{"role": "user", "content": conteudo}],
            # effort baixo: extrair e classificar uma linha curta não pede raciocínio longo
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": esquema}},
        )
    except anthropic.APIError as erro:
        raise ErroIA(str(erro)) from erro

    if resposta.stop_reason != "end_turn":
        log.warning("resposta da IA incompleta", extra={"stop_reason": resposta.stop_reason})
        return None
    texto = next((b.text for b in resposta.content if b.type == "text"), "")
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        log.warning("JSON inválido vindo da IA")
        return None
    return dados if isinstance(dados, dict) else None
