"""Dublês da API do Claude: respostas prontas, sem rede e sem custo."""

import json
from typing import Any, cast

import anthropic
from anthropic.types import Message


def mensagem(dados: dict[str, Any] | str, stop_reason: str = "end_turn") -> Message:
    texto = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
    return Message.model_validate(
        {
            "id": "msg_teste",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": texto}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 300, "output_tokens": 40},
        }
    )


class _Mensagens:
    def __init__(self, respostas: list[Message | Exception]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Message:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class ClienteFalso:
    def __init__(self, *respostas: Message | Exception) -> None:
        self.messages = _Mensagens(list(respostas))

    @property
    def chamadas(self) -> list[dict[str, Any]]:
        return self.messages.chamadas

    def como_anthropic(self) -> anthropic.Anthropic:
        return cast(anthropic.Anthropic, self)
