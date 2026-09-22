# migrar_a_supabase.py
"""Copia los datos de tu alex_bets.db local (SQLite, la base que usaba la
app antes de esta migración) a la base de datos Postgres/Supabase configurada
en DATABASE_URL. Consérvalo como paso único: ejecútalo UNA VEZ, después de
crear el proyecto en Supabase y de rellenar .streamlit/secrets.toml, y antes
de empezar a usar la app ya migrada, para no perder tu historial.

    .\\venv\\Scripts\\python.exe migrar_a_supabase.py

Si la base de datos de Supabase ya tiene alguna surebet (por ejemplo porque
ya ejecutaste este script antes), no hace nada, para no duplicar datos.
"""

import sqlite3
from pathlib import Path

import database as db  # ya apunta a Postgres/Supabase vía DATABASE_URL

SQLITE_PATH = Path(__file__).parent / "alex_bets.db"


def _filas_sqlite(conn, query):
    return [dict(fila) for fila in conn.execute(query)]


def migrar():
    if not SQLITE_PATH.exists():
        print(f"No existe {SQLITE_PATH}, no hay nada que migrar.")
        return

    origen = sqlite3.connect(SQLITE_PATH)
    origen.row_factory = sqlite3.Row
    try:
        surebets = _filas_sqlite(origen, "SELECT * FROM surebets ORDER BY id")
        patas = _filas_sqlite(origen, "SELECT * FROM patas ORDER BY id")
        oportunidades = _filas_sqlite(origen, "SELECT * FROM oportunidades ORDER BY id")
        oportunidad_patas = _filas_sqlite(origen, "SELECT * FROM oportunidad_patas ORDER BY id")
    finally:
        origen.close()

    db.init_db()

    with db.get_conn() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM surebets")
        if cur.fetchone()["n"] > 0:
            print(
                "La base de datos de Supabase ya tiene surebets guardadas. "
                "Cancelado para no duplicar (probablemente ya migraste antes)."
            )
            return

    with db.get_conn() as cur:
        id_map_surebets = {}
        for s in surebets:
            cur.execute(
                """INSERT INTO surebets
                   (fecha, evento, deporte, mercado, importe_total, beneficio_esperado_pct,
                    beneficio_esperado_importe, estado, beneficio_real, notas, creado_en)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    s["fecha"], s["evento"], s.get("deporte", ""), s["mercado"], s["importe_total"],
                    s["beneficio_esperado_pct"], s["beneficio_esperado_importe"], s["estado"],
                    s["beneficio_real"], s["notas"], s["creado_en"],
                ),
            )
            id_map_surebets[s["id"]] = cur.fetchone()["id"]

        for p in patas:
            cur.execute(
                """INSERT INTO patas
                   (surebet_id, casa_apuestas, seleccion, cuota, importe, resultado, importe_cierre)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    id_map_surebets[p["surebet_id"]], p["casa_apuestas"], p["seleccion"],
                    p["cuota"], p["importe"], p["resultado"], p.get("importe_cierre"),
                ),
            )

        id_map_oportunidades = {}
        for o in oportunidades:
            cur.execute(
                """INSERT INTO oportunidades
                   (recibido_en, roi_pct, torneo, evento, comienza_en, empieza_en,
                    texto_original, firma, usada)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    o["recibido_en"], o["roi_pct"], o["torneo"], o["evento"], o["comienza_en"],
                    o["empieza_en"], o["texto_original"], o["firma"], o["usada"],
                ),
            )
            id_map_oportunidades[o["id"]] = cur.fetchone()["id"]

        for op in oportunidad_patas:
            cur.execute(
                """INSERT INTO oportunidad_patas (oportunidad_id, casa_apuestas, seleccion, cuota)
                   VALUES (%s, %s, %s, %s)""",
                (
                    id_map_oportunidades[op["oportunidad_id"]], op["casa_apuestas"],
                    op["seleccion"], op["cuota"],
                ),
            )

    print(
        f"Migrados {len(surebets)} surebets, {len(patas)} patas, "
        f"{len(oportunidades)} oportunidades y {len(oportunidad_patas)} patas de oportunidad."
    )


if __name__ == "__main__":
    migrar()
