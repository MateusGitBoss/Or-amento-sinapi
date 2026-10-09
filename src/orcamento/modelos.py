"""Formatos de dados que circulam entre extração, escolha e orçamento."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Unidades no padrão do SINAPI que a extração pode devolver
UNIDADES = ("UN", "KG", "T", "M", "M2", "M3", "L", "SC", "MIL", "H", "CJ", "PC")

Confianca = Literal["alta", "media", "baixa"]


class ItemExtraido(BaseModel):
    """Uma linha da lista de materiais já entendida: quanto, em que unidade, de quê."""

    quantidade: Decimal = Field(gt=0)
    unidade: str | None = None
    descricao: str = Field(min_length=2)


class Escolha(BaseModel):
    """Qual insumo do SINAPI corresponde ao item (ou nenhum) e com que confiança."""

    codigo: str | None
    confianca: Confianca
    motivo: str = ""
