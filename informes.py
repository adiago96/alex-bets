# informes.py
"""Informes descargables (PDF) a partir de los datos del historial."""

from datetime import date, datetime

import pandas as pd
from fpdf import FPDF


def _eur(valor: float, signo: bool = False) -> str:
    """Formato español: 1.234,56 € (con signo + opcional)."""
    texto = f"{valor:{'+' if signo else ''},.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €"


def pdf_beneficio_por_casa(resumen: pd.DataFrame, desde: date | None, hasta: date | None) -> bytes:
    """PDF con el beneficio obtenido en cada casa de apuestas (solo surebets resueltas),
    pensado para adjuntar a la declaración de la renta.

    `resumen` necesita las columnas casa_apuestas, apuestas, apostado, devuelto y beneficio."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.core_fonts_encoding = "windows-1252"  # para el símbolo €
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Beneficio por casa de apuestas", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    if desde and hasta:
        periodo = f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y} (fecha del evento)"
    else:
        periodo = "Todo el historial"
    pdf.cell(0, 6, f"Periodo: {periodo}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Generado el {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    columnas = [("Casa de apuestas", 62, "L"), ("Nº apuestas", 24, "R"), ("Apostado", 34, "R"),
                ("Devuelto", 34, "R"), ("Beneficio", 36, "R")]
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    for titulo, ancho, alin in columnas:
        pdf.cell(ancho, 8, titulo, border=1, align=alin, fill=True)
    pdf.ln()

    pdf.set_font("helvetica", "", 10)
    for _, fila in resumen.iterrows():
        valores = [str(fila["casa_apuestas"]), str(int(fila["apuestas"])), _eur(fila["apostado"]),
                   _eur(fila["devuelto"]), _eur(fila["beneficio"], signo=True)]
        for (_, ancho, alin), valor in zip(columnas, valores):
            pdf.cell(ancho, 7, valor, border=1, align=alin)
        pdf.ln()

    pdf.set_font("helvetica", "B", 10)
    totales = ["Total", str(int(resumen["apuestas"].sum())), _eur(resumen["apostado"].sum()),
               _eur(resumen["devuelto"].sum()), _eur(resumen["beneficio"].sum(), signo=True)]
    for (_, ancho, alin), valor in zip(columnas, totales):
        pdf.cell(ancho, 8, valor, border=1, align=alin, fill=True)
    pdf.ln(12)

    ganancias = resumen.loc[resumen["beneficio"] > 0, "beneficio"].sum()
    perdidas = -resumen.loc[resumen["beneficio"] < 0, "beneficio"].sum()
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 7, "Resumen", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    for etiqueta, valor in [
        ("Suma de casas con ganancia", _eur(ganancias)),
        ("Suma de casas con pérdida", _eur(perdidas)),
        ("Resultado neto", _eur(ganancias - perdidas, signo=True)),
    ]:
        pdf.cell(70, 7, etiqueta)
        pdf.cell(40, 7, valor, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(
        0, 4,
        "Solo se incluyen apuestas de surebets ya resueltas cuyo evento está dentro del periodo. "
        "Apostado es el importe jugado en la casa, devuelto lo que pagó la casa (premio, importe "
        "anulado o cashout) y beneficio = devuelto - apostado. Las apuestas pendientes no se incluyen.",
    )
    return bytes(pdf.output())
