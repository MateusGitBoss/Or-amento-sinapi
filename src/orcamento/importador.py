"""Importa a planilha de insumos do SINAPI (Caixa) para o Postgres.

A planilha oficial tem linhas de título antes da tabela e já mudou de layout ao longo dos
anos. Por isso o importador procura a linha de cabeçalho em vez de assumir uma posição fixa,
e o mapeamento de colunas fica num lugar só (COLUNAS).
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from orcamento.db import Conexao
from orcamento.texto import normalizar

log = logging.getLogger(__name__)

# Nome da coluna no nosso banco -> trechos que identificam a coluna na planilha
COLUNAS = {
    "codigo": ("codigo",),
    "descricao": ("descricao",),
    "unidade": ("unidade",),
    "preco": ("preco mediano", "preco"),
}


class ErroPlanilha(Exception):
    """Planilha fora do formato esperado. A mensagem diz o que faltou."""


@dataclass(frozen=True)
class ResultadoImportacao:
    uf: str
    referencia: date
    linhas: int
    descartadas: int


def _achar_cabecalho(bruto: pd.DataFrame) -> int:
    for indice, linha in bruto.head(30).iterrows():
        textos = [normalizar(str(v)) for v in linha.tolist() if pd.notna(v)]
        if any(t.startswith("codigo") for t in textos) and any("descricao" in t for t in textos):
            return int(str(indice))
    raise ErroPlanilha("cabeçalho com CODIGO e DESCRICAO não encontrado nas 30 primeiras linhas")


def _mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    normalizados = [normalizar(c) for c in cabecalho]
    mapa: dict[str, int] = {}
    for destino, trechos in COLUNAS.items():
        for trecho in trechos:
            achou = next((i for i, c in enumerate(normalizados) if trecho in c), None)
            if achou is not None:
                mapa[destino] = achou
                break
        else:
            raise ErroPlanilha(f"coluna '{destino}' não encontrada no cabeçalho: {cabecalho}")
    return mapa


def preco_para_centavos(valor: object) -> int | None:
    """Aceita 1234.5 (número do Excel), '1.234,50' e '1234,50'. Inválido devolve None."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, int | float):
        texto = repr(float(valor))
    else:
        texto = str(valor).strip().replace("R$", "").strip()
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
    try:
        reais = Decimal(texto)
    except InvalidOperation:
        return None
    if reais < 0:
        return None
    return int((reais * 100).quantize(Decimal(1)))


def ler_planilha(caminho: Path) -> tuple[pd.DataFrame, int]:
    """Devolve (insumos limpos, quantidade de linhas descartadas)."""
    if caminho.suffix.lower() == ".csv":
        bruto = pd.read_csv(caminho, sep=";", header=None, dtype=str, keep_default_na=False)
    else:
        bruto = pd.read_excel(caminho, header=None, dtype=object)
    linha_cabecalho = _achar_cabecalho(bruto)
    mapa = _mapear_colunas([str(v) for v in bruto.iloc[linha_cabecalho].tolist()])

    corpo = bruto.iloc[linha_cabecalho + 1 :]
    dados = pd.DataFrame(
        {
            "codigo": corpo.iloc[:, mapa["codigo"]].map(_limpar_codigo),
            "descricao": corpo.iloc[:, mapa["descricao"]].astype(str).str.strip(),
            "unidade": corpo.iloc[:, mapa["unidade"]].astype(str).str.strip().str.upper(),
            "preco_centavos": corpo.iloc[:, mapa["preco"]].map(preco_para_centavos),
        }
    )
    validas = (
        dados["codigo"].ne("")
        & dados["descricao"].ne("")
        & dados["descricao"].ne("nan")
        & dados["preco_centavos"].notna()
    )
    limpos = dados[validas].drop_duplicates(subset="codigo", keep="first").copy()
    limpos["preco_centavos"] = limpos["preco_centavos"].astype(int)
    limpos["descricao_busca"] = limpos["descricao"].map(normalizar)
    return limpos, int(len(dados) - len(limpos))


def _limpar_codigo(valor: object) -> str:
    """Código vem como 1379, 1379.0 ou '00001379'. Guardamos sempre '1379'."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.lstrip("0") if texto.isdigit() else ""


def importar(conn: Conexao, caminho: Path, uf: str, referencia: date) -> ResultadoImportacao:
    """Idempotente por (UF, mês): reimportar o mesmo mês substitui os preços, não duplica."""
    referencia = referencia.replace(day=1)
    insumos, descartadas = ler_planilha(caminho)
    if insumos.empty:
        raise ErroPlanilha("nenhum insumo válido na planilha")

    with conn.transaction():
        conn.execute(
            "DELETE FROM insumos_sinapi WHERE uf = %s AND referencia = %s", (uf, referencia)
        )
        # COPY é o jeito mais rápido de carregar milhares de linhas no Postgres
        colunas = "uf, referencia, codigo, descricao, unidade, preco_centavos, descricao_busca"
        with (
            conn.cursor() as cursor,
            cursor.copy(f"COPY insumos_sinapi ({colunas}) FROM STDIN") as copia,
        ):
            for linha in insumos.itertuples(index=False):
                copia.write_row(
                    (
                        uf,
                        referencia,
                        linha.codigo,
                        linha.descricao,
                        linha.unidade,
                        linha.preco_centavos,
                        linha.descricao_busca,
                    )
                )
        conn.execute(
            """
            INSERT INTO importacoes (uf, referencia, arquivo, linhas)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (uf, referencia)
            DO UPDATE SET arquivo = EXCLUDED.arquivo, linhas = EXCLUDED.linhas,
                          importado_em = now()
            """,
            (uf, referencia, caminho.name, len(insumos)),
        )
    log.info(
        "planilha importada",
        extra={"uf": uf, "referencia": str(referencia), "linhas": len(insumos)},
    )
    return ResultadoImportacao(uf, referencia, len(insumos), descartadas)


def ultima_referencia(conn: Conexao, uf: str) -> date | None:
    linha = conn.execute(
        "SELECT max(referencia) AS ref FROM insumos_sinapi WHERE uf = %s", (uf,)
    ).fetchone()
    return linha["ref"] if linha else None
