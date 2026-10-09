"""Mede o orçamentista contra um gabarito: o número que diz se uma mudança melhorou ou piorou.

Três resultados por linha:
- acerto: escolheu o código certo e não pediu revisão (ou pediu revisão quando o gabarito
  diz que não existe insumo correspondente);
- revisão: mandou para revisão humana um item que tinha resposta (custa tempo, não dinheiro);
- erro calado: escolheu o código errado SEM pedir revisão. É o pior erro: entra no total
  e ninguém confere. A meta é zero.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from orcamento.orcamento import LinhaOrcamento, Orcamentista


@dataclass(frozen=True)
class CasoAvaliacao:
    linha: str
    codigo_esperado: str | None


@dataclass(frozen=True)
class ResultadoCaso:
    caso: CasoAvaliacao
    obtido: LinhaOrcamento

    @property
    def tipo(self) -> str:
        esperado, obtido = self.caso.codigo_esperado, self.obtido
        if esperado is None:
            return "acerto" if obtido.revisar else "erro_calado"
        if obtido.revisar:
            return "revisao"
        return "acerto" if obtido.codigo == esperado else "erro_calado"


@dataclass
class Relatorio:
    resultados: list[ResultadoCaso] = field(default_factory=list)

    def _contar(self, tipo: str) -> int:
        return sum(1 for r in self.resultados if r.tipo == tipo)

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def acertos(self) -> int:
        return self._contar("acerto")

    @property
    def revisoes(self) -> int:
        return self._contar("revisao")

    @property
    def erros_calados(self) -> int:
        return self._contar("erro_calado")

    def percentual(self, quantidade: int) -> float:
        return 100 * quantidade / self.total if self.total else 0.0


def carregar_conjunto(caminho: Path) -> list[CasoAvaliacao]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [
            CasoAvaliacao(
                linha=r["linha"].strip(), codigo_esperado=r["codigo_esperado"].strip() or None
            )
            for r in csv.DictReader(arquivo, delimiter=";")
            if r["linha"].strip()
        ]


def avaliar(orcamentista: Orcamentista, casos: list[CasoAvaliacao]) -> Relatorio:
    return Relatorio([ResultadoCaso(c, orcamentista.orcar_linha(c.linha)) for c in casos])
