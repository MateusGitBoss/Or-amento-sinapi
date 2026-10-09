"""Normalização de texto usada na importação e na busca: as duas pontas precisam bater."""

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaços simples: 'Cimento  CP-II' -> 'cimento cp-ii'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().lower()
