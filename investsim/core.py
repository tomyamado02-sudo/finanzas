"""
Lógica de cálculo compartida entre la CLI y la app web.
"""

import math
from datetime import date, datetime

ANNUAL_RATES = {
    "caucion":     0.75,
    "moneyMarket": 0.70,
    "spy":         0.105,   # retorno en USD; se ajusta con devaluación del peso
    "qqq":         0.145,   # retorno en USD; se ajusta con devaluación del peso
}

INVESTMENT_PROFILES = {
    "caucion": {
        "name": "Caución Bursátil",
        "monthly_return": 0.048,
        "risk": "Muy bajo",
        "risk_color": "green",
    },
    "moneyMarket": {
        "name": "Fondo Money Market",
        "monthly_return": 0.045,
        "risk": "Bajo",
        "risk_color": "green",
    },
    "spy": {
        "name": "SPY (S&P 500)",
        "monthly_return": 0.0084,   # retorno mensual base en USD
        "risk": "Moderado",
        "risk_color": "yellow",
    },
    "qqq": {
        "name": "QQQ (Nasdaq 100)",
        "monthly_return": 0.0113,   # retorno mensual base en USD
        "risk": "Alto",
        "risk_color": "orange3",
    },
    "apuestas": {
        "name": "Apuestas Online",
        "monthly_loss_rate": 0.15,
        "risk": "Muy alto",
        "risk_color": "red",
    },
}

INSTRUMENT_ORDER = ["caucion", "moneyMarket", "spy", "qqq", "apuestas"]


# ─── Simulador futuro ──────────────────────────────────────────────────────────

def generate_simulation(amount: float, months: int, annual_devaluation: float = 0.30) -> list[dict]:
    """
    Genera evolución mes a mes en ARS.
    SPY y QQQ usan retorno compuesto: (1 + USD_return) × (1 + devaluación_mensual) - 1,
    reflejando el comportamiento de CEDEARs en pesos argentinos.
    """
    monthly_dev     = (1 + annual_devaluation) ** (1 / 12) - 1
    spy_monthly_ars = (1 + INVESTMENT_PROFILES["spy"]["monthly_return"]) * (1 + monthly_dev) - 1
    qqq_monthly_ars = (1 + INVESTMENT_PROFILES["qqq"]["monthly_return"]) * (1 + monthly_dev) - 1

    data = []
    for month in range(months + 1):
        entry = {
            "month": month,
            "label": "Inicio" if month == 0 else f"Mes {month}",
        }
        entry["caucion"]     = amount * (1 + INVESTMENT_PROFILES["caucion"]["monthly_return"]) ** month
        entry["moneyMarket"] = amount * (1 + INVESTMENT_PROFILES["moneyMarket"]["monthly_return"]) ** month

        spy_variance = 1 + math.sin(month * 0.8) * 0.02
        entry["spy"]  = amount * (1 + spy_monthly_ars) ** month * spy_variance

        qqq_variance = 1 + math.sin(month * 1.2) * 0.03
        entry["qqq"]  = amount * (1 + qqq_monthly_ars) ** month * qqq_variance

        if month == 0:
            entry["apuestas"] = amount
        else:
            prev         = data[month - 1]["apuestas"]
            monthly_loss = 0.10 + math.sin(month * 2.5) * 0.05
            entry["apuestas"] = max(prev * (1 - monthly_loss), 0)
        data.append(entry)
    return data


def calculate_final_results(amount: float, months: int, annual_devaluation: float = 0.30) -> dict:
    simulation = generate_simulation(amount, months, annual_devaluation)
    final      = simulation[-1]
    results    = {}
    for key in INSTRUMENT_ORDER:
        final_amount = final[key]
        results[key] = {
            **INVESTMENT_PROFILES[key],
            "final_amount":   final_amount,
            "profit":         final_amount - amount,
            "return_percent": ((final_amount - amount) / amount) * 100,
        }
    return results


# ─── Simulador histórico ───────────────────────────────────────────────────────

def days_between(date_from: date, date_to: date) -> int:
    return max((date_to - date_from).days, 0)


def calculate_historical_alternatives(
    bet: dict, end_date: date, annual_devaluation: float = 0.30
) -> dict:
    """
    Calcula alternativas de inversión para una apuesta histórica en ARS.
    SPY y QQQ ajustan la tasa anual sumando la devaluación del peso esperada.
    """
    start = (
        bet["date"]
        if isinstance(bet["date"], date)
        else datetime.fromisoformat(bet["date"]).date()
    )
    end = (
        end_date
        if isinstance(end_date, date)
        else datetime.fromisoformat(str(end_date)).date()
    )
    days = days_between(start, end)

    # Tasas anuales ajustadas a ARS para SPY y QQQ
    annual_rates_ars = dict(ANNUAL_RATES)
    annual_rates_ars["spy"] = (1 + ANNUAL_RATES["spy"]) * (1 + annual_devaluation) - 1
    annual_rates_ars["qqq"] = (1 + ANNUAL_RATES["qqq"]) * (1 + annual_devaluation) - 1

    results = {}
    for key, rate in annual_rates_ars.items():
        daily_factor = (1 + rate) ** (1 / 365)
        final_amount = bet["amount"] * daily_factor ** days
        results[key] = {
            "final_amount":   final_amount,
            "profit":         final_amount - bet["amount"],
            "return_percent": ((final_amount - bet["amount"]) / bet["amount"]) * 100,
            "days":           days,
        }
    results["apuestas"] = {
        "final_amount":   bet["result"],
        "profit":         bet["result"] - bet["amount"],
        "return_percent": (
            ((bet["result"] - bet["amount"]) / bet["amount"]) * 100
            if bet["amount"] else 0
        ),
        "days": days,
    }
    return results


def aggregate_historical_bets(
    bets: list[dict], end_date: date, annual_devaluation: float = 0.30
) -> dict:
    totals = {
        k: {"final_amount": 0, "profit": 0, "invested": 0}
        for k in list(ANNUAL_RATES.keys()) + ["apuestas"]
    }
    total_invested = 0
    for bet in bets:
        alts = calculate_historical_alternatives(bet, end_date, annual_devaluation)
        total_invested += bet["amount"]
        for key in totals:
            totals[key]["final_amount"] += alts[key]["final_amount"]
            totals[key]["profit"]       += alts[key]["profit"]
            totals[key]["invested"]     += bet["amount"]
    for key in totals:
        inv = totals[key]["invested"]
        totals[key]["return_percent"] = (totals[key]["profit"] / inv * 100) if inv else 0
    return {"totals": totals, "total_invested": total_invested}
