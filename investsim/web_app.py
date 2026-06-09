"""
InvestSim — Web App (FastAPI)
Servir en: python3 web_app.py  →  http://localhost:8000
"""

import csv
import io
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Tuple

import httpx
import openpyxl
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import uvicorn

from .core import (
    INVESTMENT_PROFILES,
    INSTRUMENT_ORDER,
    generate_simulation,
    calculate_final_results,
    aggregate_historical_bets,
)

app = FastAPI(title="InvestSim")


# ─── HTML ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = Path(__file__).resolve().parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")


# ─── Tipo de cambio ───────────────────────────────────────────────────────────

_exchange_cache: dict = {"rate": 1050.0, "timestamp": 0.0}
_CACHE_TTL = 3600  # 1 hora


async def _fetch_exchange_rate() -> float:
    """Cotización dólar MEP desde dolarapi.com con caché de 1 hora."""
    if time.time() - _exchange_cache["timestamp"] < _CACHE_TTL:
        return _exchange_cache["rate"]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://dolarapi.com/v1/dolares/bolsa")
            if resp.status_code == 200:
                data = resp.json()
                _exchange_cache["rate"]      = float(data.get("venta", 1050.0))
                _exchange_cache["timestamp"] = time.time()
    except Exception:
        pass  # Retiene valor cacheado si la API no responde
    return _exchange_cache["rate"]


@app.get("/api/exchange-rate")
async def api_exchange_rate():
    rate = await _fetch_exchange_rate()
    return {"rate": rate, "source": "dolarapi.com"}


# ─── Plantilla de ejemplo para carga de apuestas ──────────────────────────────

_TEMPLATE_CSV = (
    "fecha,monto,recuperado\n"
    "2024-01-15,5000,0\n"
    "2024-02-20,8000,3200\n"
    "2024-03-10,4000,4000\n"
    "2024-05-01,12000,0\n"
)


@app.get("/api/bets-template.csv")
async def bets_template():
    return Response(
        content=_TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="plantilla_apuestas.csv"'},
    )


# ─── Carga de historial desde archivo ─────────────────────────────────────────

# Alias de columnas aceptados (todos se normalizan a minúsculas sin espacios)
_COL_ALIASES = {
    "fecha":      ["fecha", "date", "dia", "day"],
    "monto":      ["monto", "amount", "apostado", "apuesta", "invertido"],
    "recuperado": ["recuperado", "result", "resultado", "ganancia", "retorno", "recibido"],
}


def _norm(col) -> str:
    if col is None:
        return ""
    return str(col).strip().lower().replace(" ", "_").replace("-", "_")


def _find_col(headers: list, field: str) -> Optional[str]:
    """Devuelve el nombre original del header que coincide con el campo buscado."""
    for h in headers:
        if _norm(h) in _COL_ALIASES.get(field, []):
            return h
    return None


def _parse_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace("\xa0", "").replace(" ", "")
    # Parseo directo
    try:
        return float(s)
    except ValueError:
        pass
    # Formato argentino: "1.500" o "1.500,50"
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        pass
    # Formato US: "1,500" o "1,500.50"
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _parse_rows(rows: list[dict]) -> Tuple[list, list]:
    if not rows:
        return [], ["El archivo está vacío."]

    headers   = list(rows[0].keys())
    col_fecha = _find_col(headers, "fecha")
    col_monto = _find_col(headers, "monto")
    col_rec   = _find_col(headers, "recuperado")

    missing = [f for f, c in [("fecha", col_fecha), ("monto", col_monto), ("recuperado", col_rec)] if not c]
    if missing:
        return [], [
            f"Columnas faltantes: {', '.join(missing)}. "
            f"Se esperan las columnas: fecha, monto, recuperado."
        ]

    bets   = []
    errors = []
    today  = date.today()

    for i, row in enumerate(rows, 1):
        # Ignorar filas completamente vacías
        if all(v is None or str(v).strip() == "" for v in row.values()):
            continue

        bet_date = _parse_date(row.get(col_fecha))
        amount   = _parse_number(row.get(col_monto))
        result   = _parse_number(row.get(col_rec, 0))

        if bet_date is None:
            errors.append(f"Fila {i}: fecha inválida — '{row.get(col_fecha)}'")
            continue
        if bet_date > today:
            errors.append(f"Fila {i}: la fecha {bet_date} no puede ser futura")
            continue
        if amount is None or amount <= 0:
            errors.append(f"Fila {i}: monto inválido — '{row.get(col_monto)}'")
            continue
        if result is None or result < 0:
            errors.append(f"Fila {i}: recuperado inválido — '{row.get(col_rec)}'")
            continue

        bets.append({"date": str(bet_date), "amount": amount, "result": result})

    if not bets and not errors:
        errors = ["El archivo no contiene filas de datos."]

    return bets, errors


@app.post("/api/upload-bets")
async def api_upload_bets(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()
    content  = await file.read()

    if not content:
        raise HTTPException(400, "El archivo está vacío.")

    rows: list[dict] = []

    if filename.endswith(".csv"):
        try:
            text   = content.decode("utf-8-sig")   # maneja BOM de Excel
            reader = csv.DictReader(io.StringIO(text))
            rows   = [dict(r) for r in reader]
        except Exception as e:
            raise HTTPException(400, f"Error al leer el CSV: {e}")

    elif filename.endswith(".xlsx"):
        try:
            wb       = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws       = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                raise HTTPException(400, "El archivo Excel está vacío.")
            headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
            rows = [
                dict(zip(headers, row))
                for row in all_rows[1:]
                if any(v is not None for v in row)
            ]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Error al leer el Excel: {e}")

    else:
        raise HTTPException(400, "El archivo debe ser .xlsx o .csv")

    bets, errors = _parse_rows(rows)
    return {"bets": bets, "count": len(bets), "errors": errors}


# ─── API: Simulador futuro ─────────────────────────────────────────────────────

class FutureRequest(BaseModel):
    amount:             float
    months:             int
    annual_devaluation: float = 0.30


@app.post("/api/future")
async def api_future(req: FutureRequest):
    simulation = generate_simulation(req.amount, req.months, req.annual_devaluation)
    results    = calculate_final_results(req.amount, req.months, req.annual_devaluation)

    clean_results = {}
    for key in INSTRUMENT_ORDER:
        r = results[key]
        clean_results[key] = {
            "name":           r["name"],
            "risk":           r["risk"],
            "final_amount":   round(r["final_amount"], 2),
            "profit":         round(r["profit"], 2),
            "return_percent": round(r["return_percent"], 2),
        }

    chart_labels = [row["label"] for row in simulation]
    chart_series = {
        key: [round(row[key], 2) for row in simulation]
        for key in INSTRUMENT_ORDER
    }

    return {
        "results":            clean_results,
        "chart_labels":       chart_labels,
        "chart_series":       chart_series,
        "amount":             req.amount,
        "months":             req.months,
        "annual_devaluation": req.annual_devaluation,
    }


# ─── API: Simulador histórico ──────────────────────────────────────────────────

class BetIn(BaseModel):
    date:   str
    amount: float
    result: float


class HistoricalRequest(BaseModel):
    bets:               list[BetIn]
    annual_devaluation: float = 0.30


@app.post("/api/historical")
async def api_historical(req: HistoricalRequest):
    bets = [
        {"date": date.fromisoformat(b.date), "amount": b.amount, "result": b.result}
        for b in req.bets
    ]
    agg = aggregate_historical_bets(bets, date.today(), req.annual_devaluation)

    totals = {}
    for key in INSTRUMENT_ORDER:
        r = agg["totals"][key]
        totals[key] = {
            "name":           INVESTMENT_PROFILES[key]["name"],
            "final_amount":   round(r["final_amount"], 2),
            "profit":         round(r["profit"], 2),
            "return_percent": round(r["return_percent"], 2),
        }

    return {
        "totals":             totals,
        "total_invested":     agg["total_invested"],
        "today":              str(date.today()),
        "annual_devaluation": req.annual_devaluation,
    }


# ─── Arranque ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
