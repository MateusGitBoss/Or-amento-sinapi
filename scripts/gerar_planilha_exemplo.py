"""Gera dados/exemplo/SINAPI_exemplo_MA_202608.xlsx a partir do CSV de exemplo.

A planilha imita o layout da planilha de insumos da Caixa: linhas de cabeçalho no topo
(título, UF, mês) antes da tabela, e preço com vírgula decimal. Os códigos e descrições
seguem o estilo do SINAPI, mas os PREÇOS SÃO FICTÍCIOS: para orçar de verdade, importe a
planilha oficial do mês em https://www.caixa.gov.br/sinapi.
"""

import csv
from pathlib import Path

from openpyxl import Workbook

PASTA = Path(__file__).parent.parent / "dados" / "exemplo"


def main() -> None:
    planilha = Workbook()
    aba = planilha.active
    assert aba is not None
    aba.title = "Insumos"
    aba.append(["SISTEMA NACIONAL DE PESQUISA DE CUSTOS E ÍNDICES DA CONSTRUÇÃO CIVIL"])
    aba.append(["PREÇOS DE INSUMOS - DADOS DE EXEMPLO (PREÇOS FICTÍCIOS)"])
    aba.append(["LOCALIDADE: MA", None, "DATA DE PREÇO: 08/2026"])
    aba.append([])
    aba.append(["CODIGO", "DESCRICAO DO INSUMO", "UNIDADE", "ORIGEM DE PRECO", "PRECO MEDIANO R$"])
    with (PASTA / "insumos_exemplo.csv").open(encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            aba.append(
                [int(linha["codigo"]), linha["descricao"], linha["unidade"], "C", linha["preco"]]
            )
    planilha.save(PASTA / "SINAPI_exemplo_MA_202608.xlsx")


if __name__ == "__main__":
    main()
