# paginas/calculadora.py
"""Calculadora rápida de importes para 2 cuotas, sin guardar nada.

Incluye una tabla de equivalencias (cuota de equilibrio, margen 0%) que se
centra automáticamente en la Cuota 1 introducida, para ver de un vistazo a
partir de qué Cuota 2 la combinación deja de ser una surebet.
"""

import streamlit as st
import streamlit.components.v1 as components

from calculos import calcular_surebet

PASO_TABLA = 0.01
CUOTA_MIN_TABLA = 1.10
CUOTA_MAX_TABLA = 10.00


def _cuota_mas_cercana_en_tabla(cuota: float) -> float:
    pasos_totales = round((CUOTA_MAX_TABLA - CUOTA_MIN_TABLA) / PASO_TABLA)
    pasos = round((cuota - CUOTA_MIN_TABLA) / PASO_TABLA)
    pasos = max(0, min(pasos, pasos_totales))
    return round(CUOTA_MIN_TABLA + pasos * PASO_TABLA, 2)


def _tabla_equivalencias_html(cuota1_resaltada: float) -> str:
    n = round((CUOTA_MAX_TABLA - CUOTA_MIN_TABLA) / PASO_TABLA)
    filas = []
    for i in range(n + 1):
        c1 = round(CUOTA_MIN_TABLA + i * PASO_TABLA, 2)
        c2_equilibrio = round(c1 / (c1 - 1), 2)
        resaltar = abs(c1 - cuota1_resaltada) < 1e-9
        id_attr = ' id="fila-resaltada"' if resaltar else ""
        estilo = 'style="background:#2ecc71;color:#0b1e12;font-weight:700;"' if resaltar else ""
        filas.append(
            f'<tr{id_attr} {estilo}>'
            f'<td style="padding:4px 12px;">{c1:.2f}</td>'
            f'<td style="padding:4px 12px;">{c2_equilibrio:.2f}</td></tr>'
        )
    filas_html = "\n".join(filas)
    return f"""
    <div style="height:420px;overflow-y:auto;border:1px solid #4b5563;border-radius:8px;
                font-family:'Source Sans Pro',sans-serif;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead style="position:sticky;top:0;background:#262730;color:#fafafa;">
          <tr>
            <th style="padding:6px 12px;text-align:left;">Cuota 1</th>
            <th style="padding:6px 12px;text-align:left;">Cuota 2 de equilibrio</th>
          </tr>
        </thead>
        <tbody style="color:#e5e7eb;">
          {filas_html}
        </tbody>
      </table>
    </div>
    <script>
      const fila = document.getElementById("fila-resaltada");
      if (fila) {{ fila.scrollIntoView({{block: "center"}}); }}
    </script>
    """


def render():
    st.subheader("Calculadora rápida (2 cuotas)")
    st.caption(
        "Introduce dos cuotas y el importe a repartir para ver cuánto apostar en cada una y "
        "obtener el mismo beneficio pase lo que pase. No se guarda nada, es solo para consultar importes."
    )

    col_izq, col_der = st.columns([1.3, 1])

    with col_izq:
        importe_total = st.number_input(
            "Importe total a repartir (€)", min_value=1.0, value=100.0, step=1.0, key="calc_importe"
        )
        c1, c2 = st.columns(2)
        cuota1 = c1.number_input("Cuota 1", min_value=1.01, value=2.00, step=0.01, format="%.2f", key="calc_cuota1")
        cuota2 = c2.number_input("Cuota 2", min_value=1.01, value=2.00, step=0.01, format="%.2f", key="calc_cuota2")

        try:
            resultado = calcular_surebet([cuota1, cuota2], importe_total)

            if resultado.es_arbitraje:
                st.success(
                    f"✅ Surebet válida. Margen: **{resultado.margen_pct:.2f}%** · "
                    f"Beneficio garantizado: **{resultado.beneficio_garantizado:.2f} €**"
                )
            else:
                st.error(
                    f"🚫 No es una surebet real (probabilidad implícita total: "
                    f"{resultado.probabilidad_implicita_total * 100:.2f}% ≥ 100%). "
                    f"Perderías {abs(resultado.beneficio_garantizado):.2f} € pase lo que pase."
                )

            m1, m2 = st.columns(2)
            m1.metric(f"Apostar a cuota {cuota1:.2f}", f"{resultado.importes[0]:.2f} €")
            m2.metric(f"Apostar a cuota {cuota2:.2f}", f"{resultado.importes[1]:.2f} €")
            st.caption(f"Retorno garantizado en cualquier caso: {resultado.retorno_garantizado:.2f} €")
        except ValueError as e:
            st.error(str(e))

    with col_der:
        cuota1_tabla = _cuota_mas_cercana_en_tabla(cuota1)
        st.markdown("**Tabla de equivalencias** (cuota de equilibrio, margen 0%)")
        st.caption(
            f"Para Cuota 1 = {cuota1_tabla:.2f}: cualquier Cuota 2 **por encima** del valor resaltado "
            "es surebet; por debajo, no lo es. La tabla se centra sola en tu Cuota 1."
        )
        components.html(_tabla_equivalencias_html(cuota1_tabla), height=440, scrolling=False)
