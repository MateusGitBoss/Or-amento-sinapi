"""Busca de insumos no Postgres: texto completo em português + semelhança por trigramas.

- Full-text (tsvector/tsquery): entende radicais ("tijolos" acha "tijolo") e ignora palavras
  vazias, mas não perdoa erro de digitação.
- Trigramas (pg_trgm): compara pedaços de 3 letras, então "cimeto" ainda parece "cimento",
  mas não sabe nada de português.
Somando as duas notas, um compensa o ponto fraco do outro.
"""

from dataclasses import dataclass
from datetime import date

from orcamento.db import Conexao
from orcamento.texto import normalizar


@dataclass(frozen=True)
class Candidato:
    codigo: str
    descricao: str
    unidade: str
    preco_centavos: int
    nota: float


# plainto_tsquery junta os termos com E (&); trocar por OU (|) deixa a busca tolerante a
# palavras que não existem na descrição ("saco", "cp2"). A ordenação pela nota resolve o resto.
SQL_BUSCA = """
WITH consulta AS (
    SELECT replace(plainto_tsquery('portuguese', %(texto)s)::text, '&', '|')::tsquery AS q
)
SELECT i.codigo, i.descricao, i.unidade, i.preco_centavos,
       ts_rank(i.tsv, consulta.q) + similarity(i.descricao_busca, %(texto)s) AS nota
  FROM insumos_sinapi i, consulta
 WHERE i.uf = %(uf)s
   AND i.referencia = %(referencia)s
   AND (i.tsv @@ consulta.q OR i.descricao_busca %% %(texto)s)
 ORDER BY nota DESC, i.codigo
 LIMIT %(limite)s
"""


def buscar_candidatos(
    conn: Conexao, texto: str, uf: str, referencia: date, limite: int = 5
) -> list[Candidato]:
    texto_busca = normalizar(texto)
    if not texto_busca:
        return []
    linhas = conn.execute(
        SQL_BUSCA,
        {"texto": texto_busca, "uf": uf, "referencia": referencia, "limite": limite},
    ).fetchall()
    return [
        Candidato(
            codigo=linha["codigo"],
            descricao=linha["descricao"],
            unidade=linha["unidade"],
            preco_centavos=linha["preco_centavos"],
            nota=float(linha["nota"]),
        )
        for linha in linhas
    ]


def obter_insumo(conn: Conexao, codigo: str, uf: str, referencia: date) -> Candidato | None:
    linha = conn.execute(
        """
        SELECT codigo, descricao, unidade, preco_centavos, 1.0 AS nota
          FROM insumos_sinapi WHERE uf = %s AND referencia = %s AND codigo = %s
        """,
        (uf, referencia, codigo),
    ).fetchone()
    return Candidato(**linha) if linha else None
