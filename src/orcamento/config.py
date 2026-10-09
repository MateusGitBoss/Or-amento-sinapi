"""Configuração lida de variáveis de ambiente (ou de um arquivo .env em desenvolvimento)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/orcamento"
    anthropic_api_key: SecretStr = SecretStr("")
    # Haiku: barato e suficiente para extrair e classificar uma linha curta
    modelo: str = "claude-haiku-5-5"

    # Estado e mês de referência padrão da tabela SINAPI
    uf: str = "MA"
    candidatos_por_item: int = 5
    log_nivel: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
