"""Linha de comando: `uv run orcamento --help`."""

import typer

from orcamento.config import get_settings
from orcamento.db import conectar, migrar
from orcamento.logs import configurar_logs

app = typer.Typer(
    help="Orçamento de obra com preços de referência do SINAPI.", no_args_is_help=True
)


@app.callback()
def inicio() -> None:
    configurar_logs(get_settings().log_nivel)


@app.command("migrar")
def comando_migrar() -> None:
    """Cria ou atualiza as tabelas no banco."""
    with conectar(get_settings().database_url) as conn:
        novas = migrar(conn)
    typer.echo(f"Migrações aplicadas: {', '.join(novas) or 'nenhuma (já estava em dia)'}")
