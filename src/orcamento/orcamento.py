"""Monta o orçamento: extração -> busca no banco -> escolha -> preço do banco -> revisão.

Regra central: o preço SEMPRE vem da tabela SINAPI no banco. A IA só interpreta o texto e
escolhe entre candidatos que o banco devolveu. Item duvidoso não entra calado no total:
vai para a lista de revisão.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from orcamento.busca import Candidato
from orcamento.escolha import Escolhedor
from orcamento.extracao import Extrator
from orcamento.modelos import Confianca

log = logging.getLogger(__name__)

Buscador = Callable[[str], list[Candidato]]

# Conversões seguras entre a unidade pedida e a unidade do SINAPI (fator multiplicador).
# Só entra aqui conversão que não depende do produto: saco de cimento pode ter 25 ou 50 kg,
# por isso SC -> KG não está na lista e vai para revisão.
CONVERSOES: dict[tuple[str, str], Decimal] = {
    ("UN", "MIL"): Decimal("0.001"),
    ("MIL", "UN"): Decimal(1000),
    ("KG", "T"): Decimal("0.001"),
    ("T", "KG"): Decimal(1000),
    ("PC", "UN"): Decimal(1),
    ("UN", "PC"): Decimal(1),
}


@dataclass(frozen=True)
class LinhaOrcamento:
    linha: str
    quantidade: Decimal | None = None
    unidade_pedida: str | None = None
    codigo: str | None = None
    descricao: str | None = None
    unidade: str | None = None
    quantidade_sinapi: Decimal | None = None
    preco_unitario_centavos: int | None = None
    subtotal_centavos: int | None = None
    confianca: Confianca = "baixa"
    revisar: bool = True
    motivo: str = ""


@dataclass
class Orcamento:
    uf: str
    referencia: date
    itens: list[LinhaOrcamento] = field(default_factory=list)

    @property
    def aprovados(self) -> list[LinhaOrcamento]:
        return [i for i in self.itens if not i.revisar]

    @property
    def para_revisar(self) -> list[LinhaOrcamento]:
        return [i for i in self.itens if i.revisar]

    @property
    def total_centavos(self) -> int:
        """Só itens aprovados. Itens em revisão aparecem à parte, nunca somados em silêncio."""
        return sum(i.subtotal_centavos or 0 for i in self.aprovados)


def converter(quantidade: Decimal, de: str | None, para: str) -> tuple[Decimal | None, str]:
    """Devolve (quantidade na unidade do SINAPI, observação). None quando não dá para converter."""
    observacao = ""
    if de is None:
        # "120 bloco de concreto" = 120 peças. Sem unidade, contamos como unidades (UN)
        de, observacao = "UN", "unidade não informada, contada como UN"
    if de == para:
        return quantidade, observacao
    fator = CONVERSOES.get((de, para))
    if fator is None:
        motivo = f"pedido em {de}, SINAPI em {para}: conversão depende do produto"
        return None, "; ".join(m for m in (observacao, motivo) if m)
    convertida = quantidade * fator
    texto = f"convertido de {quantidade} {de} para {convertida.normalize()} {para}"
    return convertida, "; ".join(m for m in (observacao, texto) if m)


def calcular_subtotal(quantidade: Decimal, preco_centavos: int) -> int:
    return int((quantidade * preco_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class Orcamentista:
    def __init__(
        self,
        extrator: Extrator,
        escolhedor: Escolhedor,
        buscar: Buscador,
        uf: str,
        referencia: date,
    ) -> None:
        self.extrator = extrator
        self.escolhedor = escolhedor
        self.buscar = buscar
        self.uf = uf
        self.referencia = referencia

    def orcar_linha(self, linha: str) -> LinhaOrcamento:
        item = self.extrator.extrair(linha)
        if item is None:
            return LinhaOrcamento(linha=linha, motivo="não entendi quantidade e material")

        candidatos = self.buscar(item.descricao)
        escolha = self.escolhedor.escolher(linha, item, candidatos)
        insumo = next((c for c in candidatos if c.codigo == escolha.codigo), None)
        base = LinhaOrcamento(
            linha=linha,
            quantidade=item.quantidade,
            unidade_pedida=item.unidade,
            confianca=escolha.confianca,
            motivo=escolha.motivo,
        )
        if insumo is None:
            return base

        quantidade_sinapi, observacao = converter(item.quantidade, item.unidade, insumo.unidade)
        motivos = [m for m in (escolha.motivo, observacao) if m]
        revisar = quantidade_sinapi is None or escolha.confianca == "baixa"
        return LinhaOrcamento(
            linha=linha,
            quantidade=item.quantidade,
            unidade_pedida=item.unidade,
            codigo=insumo.codigo,
            descricao=insumo.descricao,
            unidade=insumo.unidade,
            quantidade_sinapi=quantidade_sinapi,
            preco_unitario_centavos=insumo.preco_centavos,
            subtotal_centavos=(
                calcular_subtotal(quantidade_sinapi, insumo.preco_centavos)
                if quantidade_sinapi is not None
                else None
            ),
            confianca=escolha.confianca,
            revisar=revisar,
            motivo="; ".join(motivos),
        )

    def orcar(self, linhas: Iterable[str]) -> Orcamento:
        orcamento = Orcamento(uf=self.uf, referencia=self.referencia)
        for linha in linhas:
            if not linha.strip() or linha.lstrip().startswith("#"):
                continue
            resultado = self.orcar_linha(linha.strip())
            log.info(
                "linha orçada",
                extra={
                    "linha": resultado.linha,
                    "codigo": resultado.codigo,
                    "confianca": resultado.confianca,
                    "revisar": resultado.revisar,
                },
            )
            orcamento.itens.append(resultado)
        return orcamento
