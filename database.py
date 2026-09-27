# database.py
"""Acceso a la base de datos (PostgreSQL / Supabase) de Alex Bets.

La cadena de conexión se lee de `st.secrets["DATABASE_URL"]` (fichero
.streamlit/secrets.toml, tanto en local como en Streamlit Community Cloud) o,
si no está disponible, de la variable de entorno DATABASE_URL. Ver
.streamlit/secrets.example.toml para el formato.
"""

import os
from contextlib import contextmanager
from datetime import datetime

import psycopg2
import streamlit as st
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

SCHEMA = """
CREATE TABLE IF NOT EXISTS surebets (
    id SERIAL PRIMARY KEY,
    fecha TEXT NOT NULL,
    evento TEXT NOT NULL,
    deporte TEXT NOT NULL DEFAULT '',
    mercado TEXT NOT NULL,
    importe_total DOUBLE PRECISION NOT NULL,
    beneficio_esperado_pct DOUBLE PRECISION NOT NULL,
    beneficio_esperado_importe DOUBLE PRECISION NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | resuelta
    beneficio_real DOUBLE PRECISION,
    notas TEXT,
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patas (
    id SERIAL PRIMARY KEY,
    surebet_id INTEGER NOT NULL REFERENCES surebets(id) ON DELETE CASCADE,
    casa_apuestas TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    cuota DOUBLE PRECISION NOT NULL,
    importe DOUBLE PRECISION NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente | ganada | perdida | anulada | cerrada
    importe_cierre DOUBLE PRECISION  -- solo si resultado = 'cerrada': importe recibido al cerrar/cashout
);

CREATE INDEX IF NOT EXISTS idx_patas_surebet ON patas(surebet_id);
CREATE INDEX IF NOT EXISTS idx_surebets_estado ON surebets(estado);
CREATE INDEX IF NOT EXISTS idx_surebets_fecha ON surebets(fecha);

CREATE TABLE IF NOT EXISTS bankroll_casas (
    casa_apuestas TEXT PRIMARY KEY,
    liquido DOUBLE PRECISION NOT NULL DEFAULT 0,
    pendiente DOUBLE PRECISION NOT NULL DEFAULT 0,
    actualizado_en TEXT NOT NULL
);
"""

_pool = None


def _connection_string() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta configurar DATABASE_URL: crea .streamlit/secrets.toml (a partir de "
            ".streamlit/secrets.example.toml) con la cadena de conexion de Supabase, "
            "o define la variable de entorno DATABASE_URL."
        )
    return url


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(1, 5, _connection_string(), cursor_factory=RealDictCursor)
    return _pool


@contextmanager
def get_conn():
    """Da acceso a un cursor de la base de datos. Al salir del `with` sin
    errores, confirma la transaccion; si hay una excepcion, hace rollback."""
    conn = _get_pool().getconn()
    try:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        _get_pool().putconn(conn)


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with get_conn() as cur:
        cur.execute(SCHEMA)


def crear_surebet(fecha, evento, deporte, mercado, importe_total, beneficio_pct, beneficio_importe, notas, patas):
    """Crea una surebet junto con sus patas. `patas` es una lista de dicts
    con claves: casa_apuestas, seleccion, cuota, importe."""
    with get_conn() as cur:
        cur.execute(
            """INSERT INTO surebets
               (fecha, evento, deporte, mercado, importe_total, beneficio_esperado_pct,
                beneficio_esperado_importe, notas, creado_en)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (fecha, evento, deporte, mercado, importe_total, beneficio_pct, beneficio_importe, notas, _ahora()),
        )
        surebet_id = cur.fetchone()["id"]
        cur.executemany(
            """INSERT INTO patas (surebet_id, casa_apuestas, seleccion, cuota, importe)
               VALUES (%s, %s, %s, %s, %s)""",
            [(surebet_id, p["casa_apuestas"], p["seleccion"], p["cuota"], p["importe"]) for p in patas],
        )
        listar_surebets_pendientes.clear()
        obtener_todo_dataframe.clear()
        return surebet_id


@st.cache_data(ttl=15)
def listar_surebets_pendientes():
    with get_conn() as cur:
        cur.execute("SELECT * FROM surebets WHERE estado = 'pendiente' ORDER BY fecha DESC, id DESC")
        return cur.fetchall()


@st.cache_data(ttl=15)
def listar_patas(surebet_id):
    with get_conn() as cur:
        cur.execute("SELECT * FROM patas WHERE surebet_id = %s ORDER BY id", (surebet_id,))
        return cur.fetchall()


def actualizar_resultado_pata(pata_id, resultado, importe_cierre=None):
    with get_conn() as cur:
        cur.execute(
            "UPDATE patas SET resultado = %s, importe_cierre = %s WHERE id = %s",
            (resultado, importe_cierre, pata_id),
        )
    listar_patas.clear()
    obtener_todo_dataframe.clear()


def cerrar_surebet(surebet_id, beneficio_real):
    with get_conn() as cur:
        cur.execute(
            "UPDATE surebets SET estado = 'resuelta', beneficio_real = %s WHERE id = %s",
            (beneficio_real, surebet_id),
        )
    listar_surebets_pendientes.clear()
    obtener_todo_dataframe.clear()


def eliminar_surebet(surebet_id):
    with get_conn() as cur:
        cur.execute("DELETE FROM surebets WHERE id = %s", (surebet_id,))
    listar_surebets_pendientes.clear()
    listar_patas.clear()
    obtener_todo_dataframe.clear()


def guardar_bankroll(casa_apuestas, liquido, pendiente):
    """Fija directamente el líquido y el importe en juego de una casa de
    apuestas (crea la casa si no existía). Pensado para editarse a mano: no se
    deriva de las apuestas registradas, así siempre puede reflejar la realidad
    aunque el historial de patas esté incompleto o desactualizado."""
    with get_conn() as cur:
        cur.execute(
            """INSERT INTO bankroll_casas (casa_apuestas, liquido, pendiente, actualizado_en)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (casa_apuestas) DO UPDATE
               SET liquido = EXCLUDED.liquido, pendiente = EXCLUDED.pendiente,
                   actualizado_en = EXCLUDED.actualizado_en""",
            (casa_apuestas, liquido, pendiente, _ahora()),
        )
    listar_bankroll.clear()


@st.cache_data(ttl=15)
def listar_bankroll():
    with get_conn() as cur:
        cur.execute("SELECT * FROM bankroll_casas ORDER BY casa_apuestas")
        return cur.fetchall()


def eliminar_bankroll_casa(casa_apuestas):
    with get_conn() as cur:
        cur.execute("DELETE FROM bankroll_casas WHERE casa_apuestas = %s", (casa_apuestas,))
    listar_bankroll.clear()


@st.cache_data(ttl=20)
def obtener_todo_dataframe():
    """Devuelve todas las surebets con sus patas en formato ancho, listo para pandas.

    Construye el DataFrame a partir de las filas ya traídas como diccionarios
    (en vez de dejar que pandas ejecute la consulta él mismo con
    pd.read_sql_query): sobre una conexión psycopg2 con RealDictCursor,
    pd.read_sql_query interpreta mal las filas y duplica la cabecera como si
    fuera un registro más."""
    import pandas as pd

    with get_conn() as cur:
        cur.execute("SELECT * FROM surebets")
        filas_surebets = cur.fetchall()
        cur.execute("SELECT * FROM patas")
        filas_patas = cur.fetchall()

    columnas_surebets = [
        "id", "fecha", "evento", "deporte", "mercado", "importe_total",
        "beneficio_esperado_pct", "beneficio_esperado_importe", "estado",
        "beneficio_real", "notas", "creado_en",
    ]
    columnas_patas = [
        "id", "surebet_id", "casa_apuestas", "seleccion", "cuota", "importe",
        "resultado", "importe_cierre",
    ]
    surebets = pd.DataFrame(filas_surebets, columns=columnas_surebets)
    patas = pd.DataFrame(filas_patas, columns=columnas_patas)
    return surebets, patas
