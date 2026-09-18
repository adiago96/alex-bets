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


def crear_surebet(fecha, evento, mercado, importe_total, beneficio_pct, beneficio_importe, notas, patas):
    """Crea una surebet junto con sus patas. `patas` es una lista de dicts
    con claves: casa_apuestas, seleccion, cuota, importe."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO surebets
               (fecha, evento, mercado, importe_total, beneficio_esperado_pct,
                beneficio_esperado_importe, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fecha, evento, mercado, importe_total, beneficio_pct, beneficio_importe, notas),
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


def obtener_todo_dataframe():
    """Devuelve todas las surebets con sus patas en formato ancho, listo para pandas."""
    import pandas as pd

    with get_conn() as conn:
        surebets = pd.read_sql_query("SELECT * FROM surebets", conn)
        patas = pd.read_sql_query("SELECT * FROM patas", conn)
    return surebets, patas
