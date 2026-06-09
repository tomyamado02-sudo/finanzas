import csv
import io
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from investsim.core import (
    INVESTMENT_PROFILES,
    INSTRUMENT_ORDER,
    aggregate_historical_bets,
    calculate_final_results,
    generate_simulation,
)


def fmt_currency(value: float) -> str:
    return f"$ {value:,.0f}".replace(",", ".")


def fmt_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _norm(col) -> str:
    if col is None:
        return ""
    return str(col).strip().lower().replace(" ", "_").replace("-", "_")


def _find_col(headers: list, field: str) -> str | None:
    for h in headers:
        if _norm(h) in {
            "fecha": ["fecha", "date", "dia", "day"],
            "monto": ["monto", "amount", "apostado", "apuesta", "invertido"],
            "recuperado": ["recuperado", "result", "resultado", "ganancia", "retorno", "recibido"],
        }[field]:
            return h
    return None


def _parse_date(val) -> date | None:
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


def _parse_number(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace("\xa0", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        pass
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        pass
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _parse_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    if not rows:
        return [], ["El archivo está vacío."]

    headers = list(rows[0].keys())
    col_fecha = _find_col(headers, "fecha")
    col_monto = _find_col(headers, "monto")
    col_rec = _find_col(headers, "recuperado")

    missing = [f for f, c in [("fecha", col_fecha), ("monto", col_monto), ("recuperado", col_rec)] if not c]
    if missing:
        return [], [
            f"Columnas faltantes: {', '.join(missing)}. Se esperan las columnas: fecha, monto, recuperado."
        ]

    bets = []
    errors = []
    today = date.today()

    for i, row in enumerate(rows, 1):
        if all(v is None or str(v).strip() == "" for v in row.values()):
            continue

        bet_date = _parse_date(row.get(col_fecha))
        amount = _parse_number(row.get(col_monto))
        result = _parse_number(row.get(col_rec, 0))

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

        bets.append({"date": bet_date, "amount": amount, "result": result})

    if not bets and not errors:
        errors = ["El archivo no contiene filas de datos."]

    return bets, errors


def load_uploaded_bets(uploaded_file) -> tuple[list[dict], list[str]]:
    if uploaded_file is None:
        return [], []

    filename = uploaded_file.name.lower()
    content = uploaded_file.read()
    if not content:
        return [], ["El archivo está vacío."]

    rows: list[dict] = []
    if filename.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = [dict(r) for r in reader]
        except Exception as e:
            return [], [f"Error al leer el CSV: {e}"]
    elif filename.endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                return [], ["El archivo Excel está vacío."]
            headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
            rows = [
                dict(zip(headers, row))
                for row in all_rows[1:]
                if any(v is not None for v in row)
            ]
        except Exception as e:
            return [], [f"Error al leer el Excel: {e}"]
    else:
        return [], ["El archivo debe ser .xlsx o .csv"]

    return _parse_rows(rows)


def build_results_table(results: dict) -> list[dict]:
    table = []
    for key in INVESTMENT_PROFILES:
        item = results[key]
        table.append(
            {
                "Instrumento": item["name"],
                "Riesgo": item["risk"],
                "Capital final": fmt_currency(item["final_amount"]),
                "Ganancia / Perdida": fmt_currency(item["profit"]),
                "Retorno": fmt_percent(item["return_percent"]),
            }
        )
    return table


def build_simulation_chart(simulation: list[dict]) -> dict[str, list[float]]:
    return {
        INVESTMENT_PROFILES[key]["name"]: [round(row[key], 2) for row in simulation]
        for key in INVESTMENT_PROFILES
    }


def build_bets_table(bets: list[dict]) -> list[dict]:
    return [
        {
            "Fecha": bet["date"].isoformat() if isinstance(bet["date"], date) else str(bet["date"]),
            "Monto apostado": fmt_currency(bet["amount"]),
            "Recuperado": fmt_currency(bet["result"]),
            "Ganancia/Perdida": fmt_currency(bet["result"] - bet["amount"]),
        }
        for bet in bets
    ]


def main() -> None:
    st.set_page_config(page_title="InvestSim", page_icon="📈", layout="wide")
    st.title("InvestSim")
    st.markdown(
        "Simulador de inversión vs apuestas con historial de apuestas, carga desde Excel/CSV y gráficos interactivos."
    )

    if "bets" not in st.session_state:
        st.session_state.bets = []

    tabs = st.tabs(["Proyección futura", "Evolución mensual", "Historial de apuestas"])

    with tabs[0]:
        st.subheader("Proyección futura")
        left, right = st.columns([2, 1])
        with left:
            amount = st.number_input(
                "Capital inicial (ARS)",
                min_value=1000.0,
                value=100000.0,
                step=1000.0,
                format="%.0f",
            )
            months = st.slider("Plazo en meses", min_value=1, max_value=120, value=12)
            annual_devaluation = 0.30

            if st.button("Calcular proyección"):
                results = calculate_final_results(amount, months, annual_devaluation)
                simulation = generate_simulation(amount, months, annual_devaluation)

                st.markdown(f"### Resultados a {months} {'mes' if months == 1 else 'meses'}")
                st.table(build_results_table(results))

                best = max(results.values(), key=lambda item: item["final_amount"])
                st.success(
                    f"La mejor alternativa es **{best['name']}** con {fmt_currency(best['final_amount'])}."
                )

                st.markdown("### Gráfico de evolución")
                st.line_chart(build_simulation_chart(simulation))

                st.markdown("### Valores finales por instrumento")
                final_row = simulation[-1]
                st.table(
                    {
                        "Instrumento": [INVESTMENT_PROFILES[key]["name"] for key in INVESTMENT_PROFILES],
                        "Capital final": [fmt_currency(final_row[key]) for key in INVESTMENT_PROFILES],
                    }
                )

        with right:
            st.info("Usa este panel para comparar instrumentos y ver su evolución en pesos.")
            st.markdown(
                "- La app muestra los resultados en pesos argentinos.\n"
                "- SPY y QQQ se ajustan con una devaluación fija por defecto.\n"
                "- El gráfico coloreado refleja cada tipo de activo."
            )

    with tabs[1]:
        st.subheader("Evolución mensual")
        amount = st.number_input(
            "Capital inicial para evolución (ARS)",
            min_value=1000.0,
            value=100000.0,
            step=1000.0,
            format="%.0f",
            key="evo_amount",
        )
        months = st.slider(
            "Meses de evolución",
            min_value=1,
            max_value=60,
            value=12,
            key="evo_months",
        )
        if st.button("Generar evolución", key="evo_button"):
            simulation = generate_simulation(amount, months)
            st.line_chart(build_simulation_chart(simulation))
            st.write("### Evolución por instrumento")
            st.dataframe({
                "Período": [row["label"] for row in simulation],
                **{
                    INVESTMENT_PROFILES[key]["name"]: [fmt_currency(row[key]) for row in simulation]
                    for key in INVESTMENT_PROFILES
                },
            })

    with tabs[2]:
        st.subheader("Historial de apuestas")
        st.markdown(
            "Registra tus apuestas pasadas y compara el resultado con distintas alternativas de inversión."
        )

        with st.expander("Agregar apuesta manualmente"):
            col1, col2, col3 = st.columns(3)
            with col1:
                bet_date = st.date_input("Fecha", value=date.today())
            with col2:
                bet_amount = st.number_input(
                    "Monto apostado",
                    min_value=0.0,
                    value=1000.0,
                    step=100.0,
                    format="%.0f",
                )
            with col3:
                bet_result = st.number_input(
                    "Recuperado",
                    min_value=0.0,
                    value=0.0,
                    step=100.0,
                    format="%.0f",
                )
            if st.button("Agregar apuesta"):
                st.session_state.bets.append(
                    {"date": bet_date, "amount": bet_amount, "result": bet_result}
                )
                st.success("Apuesta agregada correctamente.")

        with st.expander("Cargar archivo Excel/CSV"):
            uploaded_file = st.file_uploader(
                "Sube un archivo .xlsx o .csv con columnas fecha, monto, recuperado",
                type=["xlsx", "csv"],
                accept_multiple_files=False,
            )
            if uploaded_file is not None:
                bets, errors = load_uploaded_bets(uploaded_file)
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    st.session_state.bets.extend(bets)
                    st.success(f"Se cargaron {len(bets)} apuestas desde el archivo.")
                    st.write("Usa el panel de abajo para ver y analizar tus apuestas cargadas.")

        if st.session_state.bets:
            st.markdown("### Apuestas registradas")
            st.table(build_bets_table(st.session_state.bets))
            if st.button("Limpiar apuestas"):
                st.session_state.bets = []
                st.experimental_rerun()

            agg = aggregate_historical_bets(st.session_state.bets, date.today())
            st.markdown("### Resultados históricos")
            cols = st.columns(len(INVESTMENT_PROFILES))
            for idx, key in enumerate(INVESTMENT_PROFILES):
                result = agg["totals"][key]
                with cols[idx]:
                    st.metric(
                        INVESTMENT_PROFILES[key]["name"],
                        fmt_currency(result["final_amount"]),
                        fmt_percent(result["profit"] / max(result["final_amount"] - result["profit"], 1) * 100),
                    )
            st.bar_chart(
                {
                    INVESTMENT_PROFILES[key]["name"]: [agg["totals"][key]["final_amount"]]
                    for key in INVESTMENT_PROFILES
                }
            )
            st.write("#### Detalle por instrumento")
            st.table(
                [
                    {
                        "Instrumento": INVESTMENT_PROFILES[key]["name"],
                        "Capital final": fmt_currency(agg["totals"][key]["final_amount"]),
                        "Ganancia / Pérdida": fmt_currency(agg["totals"][key]["profit"]),
                        "Retorno": fmt_percent(agg["totals"][key]["return_percent"]),
                    }
                    for key in INVESTMENT_PROFILES
                ]
            )
        else:
            st.info("Agrega apuestas o carga un archivo para ver el historial y comparar con inversiones.")


if __name__ == "__main__":
    main()
