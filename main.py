#!/usr/bin/env python3
"""
InvestSim — Simulador de Decisiones de Inversión (CLI)
Compará instrumentos financieros vs apuestas antes de mover dinero.
"""

from datetime import date

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.rule import Rule

from .core import (
    INVESTMENT_PROFILES,
    INSTRUMENT_ORDER,
    generate_simulation,
    calculate_final_results,
    aggregate_historical_bets,
)

console = Console()


# ─────────────────────────────────────────────
# UTILIDADES DE FORMATO
# ─────────────────────────────────────────────
def fmt_currency(value: float) -> str:
    return f"$ {value:,.0f}".replace(",", ".")


def fmt_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def profit_style(value: float) -> str:
    if value > 0:
        return "bold green"
    if value < 0:
        return "bold red"
    return "white"


def parse_amount(raw: str) -> float:
    """Acepta '100000', '100.000' o '100,000'."""
    cleaned = raw.strip().replace("$", "").replace(" ", "")
    if "." in cleaned and "," not in cleaned and len(cleaned.split(".")[-1]) == 3:
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return float(cleaned)


# ─────────────────────────────────────────────
# VISTAS
# ─────────────────────────────────────────────
def show_future_simulator():
    console.print(
        Panel(
            "[bold cyan]SIMULADOR DE INVERSIÓN FUTURA[/bold cyan]\n"
            "[dim]Proyectá tu capital en distintos instrumentos[/dim]",
            expand=False,
        )
    )
    console.print()

    while True:
        raw = Prompt.ask("  Capital inicial")
        try:
            amount = parse_amount(raw)
            if amount <= 0:
                raise ValueError
            break
        except ValueError:
            console.print("  [red]Ingresá un número válido mayor a 0.[/red]")

    while True:
        raw = Prompt.ask("  Plazo en meses", default="12")
        try:
            months = int(raw)
            if months <= 0:
                raise ValueError
            break
        except ValueError:
            console.print("  [red]Ingresá un número entero mayor a 0.[/red]")

    console.print(f"\n  [dim]Calculando escenarios...[/dim]\n")

    results = calculate_final_results(amount, months)

    table = Table(
        title=f"Resultados a {months} {'mes' if months == 1 else 'meses'} — Capital: {fmt_currency(amount)}",
        show_lines=True,
        header_style="bold white on dark_blue",
        title_style="bold",
    )
    table.add_column("Instrumento",    style="bold",     min_width=22)
    table.add_column("Riesgo",         justify="center", min_width=10)
    table.add_column("Capital final",  justify="right",  min_width=15)
    table.add_column("Ganancia/Perd.", justify="right",  min_width=15)
    table.add_column("Retorno %",      justify="right",  min_width=10)

    for key, r in results.items():
        ps = profit_style(r["profit"])
        risk_color = r["risk_color"]
        table.add_row(
            r["name"],
            f"[{risk_color}]{r['risk']}[/{risk_color}]",
            fmt_currency(r["final_amount"]),
            f"[{ps}]{fmt_currency(r['profit'])}[/{ps}]",
            f"[{ps}]{fmt_percent(r['return_percent'])}[/{ps}]",
        )

    console.print(table)

    if Confirm.ask("\n  ¿Ver evolución mes a mes?", default=False):
        simulation = generate_simulation(amount, months)
        show_monthly_evolution(simulation, amount)


def show_monthly_evolution(simulation: list[dict], amount: float):
    console.print()
    table = Table(
        title="Evolución mensual",
        show_lines=False,
        header_style="bold white on dark_blue",
    )
    table.add_column("Período",      min_width=8)
    table.add_column("Caución",      justify="right", min_width=14)
    table.add_column("Money Market", justify="right", min_width=14)
    table.add_column("SPY",          justify="right", min_width=14)
    table.add_column("QQQ",          justify="right", min_width=14)
    table.add_column("Apuestas",     justify="right", min_width=14, style="red")

    for row in simulation:
        table.add_row(
            row["label"],
            fmt_currency(row["caucion"]),
            fmt_currency(row["moneyMarket"]),
            fmt_currency(row["spy"]),
            fmt_currency(row["qqq"]),
            fmt_currency(row["apuestas"]),
        )

    console.print(table)


def show_historical_simulator():
    console.print(
        Panel(
            "[bold cyan]SIMULADOR HISTÓRICO[/bold cyan]\n"
            "[dim]¿Cuánto tendrías hoy si hubieras invertido en vez de apostar?[/dim]",
            expand=False,
        )
    )
    console.print()
    console.print(
        "  Ingresá tus apuestas pasadas.\n"
        "  Cuando termines, escribí [bold]listo[/bold] en el campo de fecha.\n"
    )

    bets = []

    while True:
        console.print(Rule(f"Apuesta #{len(bets) + 1}", style="dim"))

        date_str = Prompt.ask("  Fecha (YYYY-MM-DD) o [bold]listo[/bold]")
        if date_str.strip().lower() == "listo":
            if not bets:
                console.print("  [red]Ingresá al menos una apuesta antes de continuar.[/red]\n")
                continue
            break

        try:
            bet_date = date.fromisoformat(date_str.strip())
        except ValueError:
            console.print("  [red]Formato inválido. Usá YYYY-MM-DD, por ejemplo: 2024-03-15[/red]\n")
            continue

        if bet_date > date.today():
            console.print("  [red]La fecha no puede ser futura.[/red]\n")
            continue

        try:
            raw_amount = Prompt.ask("  Monto apostado")
            amount = parse_amount(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            console.print("  [red]Monto inválido.[/red]\n")
            continue

        try:
            raw_result = Prompt.ask("  ¿Cuánto recuperaste? (0 si perdiste todo)", default="0")
            result = parse_amount(raw_result)
            if result < 0:
                raise ValueError
        except ValueError:
            console.print("  [red]Valor inválido.[/red]\n")
            continue

        bets.append({"date": bet_date, "amount": amount, "result": result})
        console.print(f"  [green]Registrado.[/green]\n")

    hoy = date.today()
    agg = aggregate_historical_bets(bets, hoy)

    console.print(f"\n  [dim]Análisis hasta hoy ({hoy})[/dim]\n")

    if len(bets) > 1:
        det = Table(
            title="Detalle de apuestas ingresadas",
            show_lines=False,
            header_style="bold white on dark_blue",
        )
        det.add_column("Fecha",      min_width=12)
        det.add_column("Apostado",   justify="right", min_width=13)
        det.add_column("Recuperado", justify="right", min_width=13)
        det.add_column("Resultado",  justify="right", min_width=13)
        for bet in bets:
            pl = bet["result"] - bet["amount"]
            ps = profit_style(pl)
            det.add_row(
                str(bet["date"]),
                fmt_currency(bet["amount"]),
                fmt_currency(bet["result"]),
                f"[{ps}]{fmt_currency(pl)}[/{ps}]",
            )
        console.print(det)
        console.print()

    table = Table(
        title=f"Si hubieras invertido — Total apostado: {fmt_currency(agg['total_invested'])}",
        show_lines=True,
        header_style="bold white on dark_blue",
        title_style="bold",
    )
    table.add_column("Instrumento", style="bold", min_width=22)
    table.add_column("Hoy valdría", justify="right", min_width=15)
    table.add_column("Diferencia",  justify="right", min_width=15)
    table.add_column("Retorno",     justify="right", min_width=10)

    for key in INSTRUMENT_ORDER:
        r    = agg["totals"][key]
        name = INVESTMENT_PROFILES.get(key, {}).get("name", key)
        ps   = profit_style(r["profit"])
        table.add_row(
            name,
            fmt_currency(r["final_amount"]),
            f"[{ps}]{fmt_currency(r['profit'])}[/{ps}]",
            f"[{ps}]{fmt_percent(r['return_percent'])}[/{ps}]",
        )

    console.print(table)


# ─────────────────────────────────────────────
# MENÚ PRINCIPAL
# ─────────────────────────────────────────────
def show_menu() -> str:
    console.print(
        Panel(
            "[bold green]InvestSim[/bold green]  ·  Simulador de Decisiones de Inversión\n"
            "[dim]Tomá mejores decisiones financieras basadas en datos[/dim]",
            expand=False,
            border_style="green",
        )
    )
    console.print()
    console.print("  [cyan][1][/cyan]  Simular inversión futura")
    console.print("  [cyan][2][/cyan]  Analizar apuestas históricas")
    console.print("  [cyan][0][/cyan]  Salir")
    console.print()
    return Prompt.ask("  Opción", choices=["0", "1", "2"])


def main():
    while True:
        console.clear()
        choice = show_menu()
        console.print()

        if choice == "1":
            show_future_simulator()
        elif choice == "2":
            show_historical_simulator()
        elif choice == "0":
            console.print("  [dim]Hasta luego.[/dim]\n")
            break

        if choice != "0":
            Prompt.ask("\n  [dim]Enter para volver al menú[/dim]", default="")


if __name__ == "__main__":
    main()
