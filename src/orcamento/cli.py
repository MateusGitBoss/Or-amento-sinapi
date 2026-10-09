"""Linha de comando: `uv run orcamento --help`."""

from datetime import date, datetime
from pathlib import Path

import anthropic
import typer

from orcamento.avaliacao import avaliar, carregar_conjunto
from orcamento.busca import Candidato, buscar_candidatos
from orcamento.cache import CachePostgres
from orcamento.config import Settings, get_settings
from orcamento.db import Conexao, conectar, migrar
from orcamento.escolha import EscolhaIA, EscolhaRegra, Escolhedor
from orcamento.exportar import exportar
from orcamento.extracao import Extrator, ExtratorIA, ExtratorRegra
from orcamento.ia import ErroIA
from orcamento.importador import ErroPlanilha, importar, ultima_referencia
from orcamento.logs import configurar_logs
from orcamento.orcamento import Orcamentista

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


def montar_orcamentista(
    conn: Conexao, settings: Settings, referencia: date, sem_ia: bool
) -> Orcamentista:
    def buscar(texto: str) -> list[Candidato]:
        return buscar_candidatos(conn, texto, settings.uf, referencia, settings.candidatos_por_item)

    if sem_ia:
        extrator: Extrator = ExtratorRegra()
        escolhedor: Escolhedor = EscolhaRegra()
    else:
        chave = settings.anthropic_api_key.get_secret_value()
        if not chave:
            typer.echo(
                "ANTHROPIC_API_KEY não definida. Use --sem-ia para rodar só com regras.", err=True
            )
            raise typer.Exit(1)
        cliente = anthropic.Anthropic(api_key=chave, timeout=60, max_retries=2)
        cache = CachePostgres(conn)
        extrator = ExtratorIA(cliente, settings.modelo, cache)
        escolhedor = EscolhaIA(cliente, settings.modelo, cache)
    return Orcamentista(extrator, escolhedor, buscar, settings.uf, referencia)


def _referencia_ou_ultima(conn: Conexao, uf: str, referencia: str | None) -> date:
    ref = _referencia(referencia) if referencia else ultima_referencia(conn, uf)
    if ref is None:
        typer.echo(
            f"Nenhuma tabela SINAPI importada para {uf}. Rode `orcamento importar`.", err=True
        )
        raise typer.Exit(1)
    return ref


def _reais(centavos: int | None) -> str:
    if centavos is None:
        return "-"
    return f"R$ {centavos / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.command("orcar")
def comando_orcar(
    lista: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Arquivo .txt, uma linha por item"
    ),
    saida: Path = typer.Option(None, help="Salvar em .xlsx ou .csv"),
    referencia: str = typer.Option(None, help="AAAA-MM (padrão: mês mais recente importado)"),
    sem_ia: bool = typer.Option(False, "--sem-ia", help="Usar só regras, sem chamar a IA"),
) -> None:
    """Orça uma lista de materiais escrita de qualquer jeito."""
    settings = get_settings()
    with conectar(settings.database_url) as conn:
        ref = _referencia_ou_ultima(conn, settings.uf, referencia)
        orcamentista = montar_orcamentista(conn, settings, ref, sem_ia)
        try:
            orcamento = orcamentista.orcar(lista.read_text(encoding="utf-8").splitlines())
        except ErroIA as erro:
            typer.echo(f"Falha ao chamar a IA: {erro}", err=True)
            raise typer.Exit(1) from erro

    for item in orcamento.itens:
        situacao = "REVISAR" if item.revisar else "ok"
        # Item em revisão não mostra subtotal: ele não entra no total
        subtotal = _reais(None if item.revisar else item.subtotal_centavos)
        typer.echo(
            f"{situacao:<8} {item.linha[:34]:<34} {item.codigo or '-':>7} "
            f"{(item.descricao or '')[:40]:<40} {subtotal:>14}"
        )
        if item.revisar and item.motivo:
            typer.echo(f"{'':<8} motivo: {item.motivo}")
    typer.echo(
        f"\nTotal dos itens ok: {_reais(orcamento.total_centavos)} "
        f"(SINAPI {orcamento.uf} {orcamento.referencia:%m/%Y}). "
        f"Itens para revisar: {len(orcamento.para_revisar)}."
    )
    if saida:
        exportar(orcamento, saida)
        typer.echo(f"Salvo em {saida}")


@app.command("avaliar")
def comando_avaliar(
    conjunto: Path = typer.Argument(
        Path("dados/avaliacao/conjunto.csv"),
        exists=True,
        dir_okay=False,
        help="CSV linha;codigo_esperado",
    ),
    referencia: str = typer.Option(None, help="AAAA-MM (padrão: mês mais recente importado)"),
    sem_ia: bool = typer.Option(False, "--sem-ia", help="Avaliar só as regras, sem IA"),
) -> None:
    """Mede acerto, revisões e erros calados contra o gabarito."""
    settings = get_settings()
    with conectar(settings.database_url) as conn:
        ref = _referencia_ou_ultima(conn, settings.uf, referencia)
        relatorio = avaliar(
            montar_orcamentista(conn, settings, ref, sem_ia), carregar_conjunto(conjunto)
        )

    for r in relatorio.resultados:
        if r.tipo != "acerto":
            typer.echo(
                f"{r.tipo:<12} {r.caso.linha:<40} esperado={r.caso.codigo_esperado or 'nenhum'} "
                f"obtido={r.obtido.codigo or 'nenhum'} ({r.obtido.confianca})"
            )
    modo = "regras" if sem_ia else f"IA ({settings.modelo})"
    typer.echo(f"\nModo: {modo}. {relatorio.total} linhas.")
    for rotulo, quantidade in (
        ("Acertos", relatorio.acertos),
        ("Revisões", relatorio.revisoes),
        ("Erros calados", relatorio.erros_calados),
    ):
        typer.echo(f"{rotulo + ':':<15}{quantidade:>3} ({relatorio.percentual(quantidade):.0f}%)")
