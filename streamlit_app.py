import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from investsim.core import INVESTMENT_PROFILES, INSTRUMENT_ORDER, calculate_final_results, generate_simulation


def fmt_currency(value: float) -> str:
    return f"$ {value:,.0f}".replace(",", ".")


def fmt_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


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


def main() -> None:
    st.set_page_config(page_title="InvestSim", page_icon="📈", layout="centered")

    st.title("InvestSim")
    st.markdown(
        "Simulador de inversión vs. apuestas. Calcula la evolución de tu capital en distintos instrumentos financieros y en apuestas online."
    )

    tabs = st.tabs(["Proyección futura", "Evolución mensual"])

    with tabs[0]:
        st.header("Proyección futura")
        amount = st.number_input(
            "Capital inicial (ARS)",
            min_value=1000.0,
            value=100000.0,
            step=1000.0,
            format="%.0f",
        )
        months = st.slider("Plazo en meses", min_value=1, max_value=120, value=12)

        if st.button("Calcular resultados"):
            results = calculate_final_results(amount, months)
            st.write(
                f"### Resultado a {months} {'mes' if months == 1 else 'meses'} para {fmt_currency(amount)}"
            )
            st.table(build_results_table(results))

            best = max(results.values(), key=lambda item: item["final_amount"])
            st.success(
                f"La mejor alternativa es {best['name']} con {fmt_currency(best['final_amount'])}."
            )

    with tabs[1]:
        st.header("Evolución mensual")
        evolution_amount = st.number_input(
            "Capital inicial para evolución (ARS)",
            min_value=1000.0,
            value=100000.0,
            step=1000.0,
            format="%.0f",
            key="evolution_amount",
        )
        evolution_months = st.slider(
            "Meses de evolución",
            min_value=1,
            max_value=60,
            value=12,
            key="evolution_months",
        )

        if st.button("Generar evolución", key="generate_evolution"):
            simulation = generate_simulation(evolution_amount, evolution_months)
            st.write(
                "La siguiente gráfica muestra cómo cambia el capital mes a mes en cada tipo de activo."
            )

            chart_data = {
                INVESTMENT_PROFILES[key]["name"]: [row[key] for row in simulation]
                for key in INVESTMENT_PROFILES
            }
            st.line_chart(chart_data)

            st.write("### Valores finales")
            final_row = simulation[-1]
            st.table(
                {
                    "Instrumento": [INVESTMENT_PROFILES[key]["name"] for key in INVESTMENT_PROFILES],
                    "Capital final": [fmt_currency(final_row[key]) for key in INVESTMENT_PROFILES],
                }
            )


if __name__ == "__main__":
    main()
