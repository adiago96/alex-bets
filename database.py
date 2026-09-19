# database.py
"""Acceso a la base de datos SQLite de Alex Bets."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "alex_bets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS surebets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    evento TEXT NOT NULL,
    deporte TEXT NOT NULL DEFAULT '',
    mercado TEXT NOT NULL,
    importe_total REAL NOT NULL,
    beneficio_esperado_pct REAL NOT NULL,
    beneficio_esperado_importe REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | resuelta
    beneficio_real REAL,
    notas TEXT,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS patas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    surebet_id INTEGER NOT NULL REFERENCES surebets(id) ON DELETE CASCADE,
    casa_apuestas TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    cuota REAL NOT NULL,
    importe REAL NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'pendiente'  -- pendiente | ganada | perdida
);

CREATE INDEX IF NOT EXISTS idx_patas_surebet ON patas(surebet_id);
CREATE INDEX IF NOT EXISTS idx_surebets_estado ON surebets(estado);
CREATE INDEX IF NOT EXISTS idx_surebets_fecha ON surebets(fecha);

CREATE TABLE IF NOT EXISTS oportunidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recibido_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    roi_pct REAL NOT NULL,
    torneo TEXT NOT NULL,
    evento TEXT NOT NULL,
    comienza_en TEXT NOT NULL,   -- texto original del canal, ej. "5h 37m" (solo informativo)
    empieza_en TEXT,             -- fecha/hora absoluta calculada al recibir el mensaje, para filtrar
    texto_original TEXT NOT NULL,
    firma TEXT NOT NULL,         -- evento + casas/selecciones, para detectar duplicados
    usada INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oportunidad_patas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oportunidad_id INTEGER NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    casa_apuestas TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    cuota REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oportunidad_patas_oportunidad ON oportunidad_patas(oportunidad_id);
CREATE INDEX IF NOT EXISTS idx_oportunidades_usada ON oportunidades(usada);
CREATE INDEX IF NOT EXISTS idx_oportunidades_firma ON oportunidades(firma);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        columnas = {fila["name"] for fila in conn.execute("PRAGMA table_info(surebets)")}
        if "deporte" not in columnas:
            conn.execute("ALTER TABLE surebets ADD COLUMN deporte TEXT NOT NULL DEFAULT ''")


def crear_surebet(fecha, evento, deporte, mercado, importe_total, beneficio_pct, beneficio_importe, notas, patas):
    """Crea una surebet junto con sus patas. `patas` es una lista de dicts
    con claves: casa_apuestas, seleccion, cuota, importe."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO surebets
               (fecha, evento, deporte, mercado, importe_total, beneficio_esperado_pct,
                beneficio_esperado_importe, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, evento, deporte, mercado, importe_total, beneficio_pct, beneficio_importe, notas),
        )
        surebet_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO patas (surebet_id, casa_apuestas, seleccion, cuota, importe)
               VALUES (?, ?, ?, ?, ?)""",
            [(surebet_id, p["casa_apuestas"], p["seleccion"], p["cuota"], p["importe"]) for p in patas],
        )
        return surebet_id


def listar_surebets_pendientes():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM surebets WHERE estado = 'pendiente' ORDER BY fecha DESC, id DESC"
        ).fetchall()


def listar_patas(surebet_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM patas WHERE surebet_id = ? ORDER BY id", (surebet_id,)
        ).fetchall()


def actualizar_resultado_pata(pata_id, resultado):
    with get_conn() as conn:
        conn.execute("UPDATE patas SET resultado = ? WHERE id = ?", (resultado, pata_id))


def cerrar_surebet(surebet_id, beneficio_real):
    with get_conn() as conn:
        conn.execute(
            "UPDATE surebets SET estado = 'resuelta', beneficio_real = ? WHERE id = ?",
            (beneficio_real, surebet_id),
        )


def eliminar_surebet(surebet_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM surebets WHERE id = ?", (surebet_id,))


def firma_oportunidad(evento, patas):
    """Clave para detectar si dos mensajes describen la misma oportunidad:
    mismo evento y mismas combinaciones casa/selección, sin importar el orden."""
    combinaciones = sorted(f"{p['casa_apuestas']}::{p['seleccion']}" for p in patas)
    return evento + "||" + "|".join(combinaciones)


def guardar_oportunidad(roi_pct, torneo, evento, comienza_en, empieza_en, texto_original, patas):
    """Guarda una oportunidad detectada en Telegram junto con sus patas. Si ya
    existe una oportunidad no caducada con el mismo evento y las mismas
    casas/selecciones, la actualiza (refresca ROI, cuotas y hora) en vez de
    duplicarla. `patas` es una lista de dicts con claves: casa_apuestas,
    seleccion, cuota."""
    firma = firma_oportunidad(evento, patas)
    with get_conn() as conn:
        existente = conn.execute(
            """SELECT id FROM oportunidades
               WHERE firma = ? AND (empieza_en IS NULL OR empieza_en > datetime('now', 'localtime'))""",
            (firma,),
        ).fetchone()

        if existente:
            oportunidad_id = existente["id"]
            conn.execute(
                """UPDATE oportunidades
                   SET roi_pct = ?, torneo = ?, comienza_en = ?, empieza_en = ?,
                       texto_original = ?, recibido_en = datetime('now', 'localtime')
                   WHERE id = ?""",
                (roi_pct, torneo, comienza_en, empieza_en, texto_original, oportunidad_id),
            )
            conn.execute("DELETE FROM oportunidad_patas WHERE oportunidad_id = ?", (oportunidad_id,))
        else:
            cur = conn.execute(
                """INSERT INTO oportunidades
                   (roi_pct, torneo, evento, comienza_en, empieza_en, texto_original, firma)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (roi_pct, torneo, evento, comienza_en, empieza_en, texto_original, firma),
            )
            oportunidad_id = cur.lastrowid

        conn.executemany(
            """INSERT INTO oportunidad_patas (oportunidad_id, casa_apuestas, seleccion, cuota)
               VALUES (?, ?, ?, ?)""",
            [(oportunidad_id, p["casa_apuestas"], p["seleccion"], p["cuota"]) for p in patas],
        )
        return oportunidad_id


def eliminar_oportunidades_caducadas():
    """Borra las oportunidades cuyo evento ya ha empezado (según empieza_en)."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM oportunidades WHERE empieza_en IS NOT NULL AND empieza_en <= datetime('now', 'localtime')"
        )


def listar_oportunidades(solo_no_usadas=True, limite=50):
    """Lista oportunidades cuyo evento todavía no ha empezado (o sin hora
    reconocida), más recientes primero por hora de inicio."""
    with get_conn() as conn:
        condiciones = ["(empieza_en IS NULL OR empieza_en > datetime('now', 'localtime'))"]
        if solo_no_usadas:
            condiciones.append("usada = 0")
        query = (
            "SELECT * FROM oportunidades WHERE " + " AND ".join(condiciones)
            + " ORDER BY empieza_en IS NULL, empieza_en ASC LIMIT ?"
        )
        return conn.execute(query, (limite,)).fetchall()


def listar_oportunidad_patas(oportunidad_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM oportunidad_patas WHERE oportunidad_id = ? ORDER BY id", (oportunidad_id,)
        ).fetchall()


def marcar_oportunidad_usada(oportunidad_id):
    with get_conn() as conn:
        conn.execute("UPDATE oportunidades SET usada = 1 WHERE id = ?", (oportunidad_id,))


def eliminar_oportunidad(oportunidad_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM oportunidades WHERE id = ?", (oportunidad_id,))


def obtener_todo_dataframe():
    """Devuelve todas las surebets con sus patas en formato ancho, listo para pandas."""
    import pandas as pd

    with get_conn() as conn:
        surebets = pd.read_sql_query("SELECT * FROM surebets", conn)
        patas = pd.read_sql_query("SELECT * FROM patas", conn)
    return surebets, patas
