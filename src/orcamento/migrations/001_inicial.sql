-- Busca por semelhança de texto (trigramas): acha "cimento cp2" mesmo com erro de digitação
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tabela de insumos do SINAPI. Uma linha por insumo, por estado, por mês de referência.
CREATE TABLE insumos_sinapi (
    uf               CHAR(2)     NOT NULL,
    referencia       DATE        NOT NULL,  -- sempre dia 1 do mês (ex.: 2026-08-01)
    codigo           TEXT        NOT NULL,
    descricao        TEXT        NOT NULL,
    unidade          TEXT        NOT NULL,
    preco_centavos   INTEGER     NOT NULL CHECK (preco_centavos >= 0),
    -- Descrição em minúsculas e sem acento, gerada no Python na importação
    descricao_busca  TEXT        NOT NULL,
    -- Índice de busca textual em português (radicais: "tijolos" e "tijolo" batem)
    tsv              TSVECTOR    GENERATED ALWAYS AS (to_tsvector('portuguese', descricao_busca)) STORED,
    PRIMARY KEY (uf, referencia, codigo)
);

CREATE INDEX ix_insumos_tsv ON insumos_sinapi USING GIN (tsv);
CREATE INDEX ix_insumos_trgm ON insumos_sinapi USING GIN (descricao_busca gin_trgm_ops);

-- Registro de cada importação: dá para saber de onde veio cada mês
CREATE TABLE importacoes (
    uf           CHAR(2)     NOT NULL,
    referencia   DATE        NOT NULL,
    arquivo      TEXT        NOT NULL,
    linhas       INTEGER     NOT NULL,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (uf, referencia)
);

-- Respostas da IA guardadas por chave (modelo + versão do prompt + entrada normalizada):
-- a mesma linha não paga de novo e o resultado é reprodutível
CREATE TABLE cache_ia (
    chave      TEXT PRIMARY KEY,
    resposta   JSONB       NOT NULL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
