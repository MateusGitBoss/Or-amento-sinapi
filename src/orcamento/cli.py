"""Linha de comando: `uv run orcamento --help`."""

from datetime import date, datetime
from pathlib import Path

import typer

from orcamento.busca import buscar_candidatos
from orcamento.config import get_settings
from orcamento.db import conectar, migrar
from orcamento.importador import ErroPlanilha, importar, ultima_referencia
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


def _referencia(texto: str) -> date:
    try:
        return datetime.strptime(texto, "%Y-%m").date()
    except ValueError as erro:
        raise typer.BadParameter("use o formato AAAA-MM, por exemplo 2026-08") from erro


@app.command("importar")
def comando_importar(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False, help="Planilha .xlsx ou .csv"),
    referencia: str = typer.Option(..., help="Mês de referência, AAAA-MM"),
    uf: str = typer.Option(None, help="UF da planilha (padrão: variável UF)"),
) -> None:
    """Importa a planilha de insumos do SINAPI de um mês. Reimportar o mesmo mês substitui."""
    settings = get_settings()
    with conectar(settings.database_url) as conn:
        try:
            resultado = importar(
                conn, arquivo, (uf or settings.uf).upper(), _referencia(referencia)
            )
        except ErroPlanilha as erro:
            typer.echo(f"Planilha inválida: {erro}", err=True)
            raise typer.Exit(1) from erro
    typer.echo(
        f"{resultado.linhas} insumos importados para {resultado.uf} "
        f"{resultado.referencia:%m/%Y} ({resultado.descartadas} linhas descartadas)."
    )


@app.command("buscar")
def comando_buscar(
    texto: str = typer.Argument(..., help="O que procurar, ex.: 'tijolo 8 furos'"),
    referencia: str = typer.Option(None, help="AAAA-MM (padrão: mês mais recente importado)"),
) -> None:
    """Mostra os insumos mais parecidos com o texto (sem IA)."""
    settings = get_settings()
    with conectar(settings.database_url) as conn:
        ref = _referencia(referencia) if referencia else ultima_referencia(conn, settings.uf)
        if ref is None:
            typer.echo(f"Nenhuma tabela SINAPI importada para {settings.uf}.", err=True)
            raise typer.Exit(1)
        for c in buscar_candidatos(conn, texto, settings.uf, ref, settings.candidatos_por_item):
            typer.echo(f"{c.nota:5.2f}  {c.codigo:>7}  {c.unidade:<4} {c.descricao}")
