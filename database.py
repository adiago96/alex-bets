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

CREATE TABLE IF NOT EXISTS movimientos_bankroll (
    id SERIAL PRIMARY KEY,
    casa_apuestas TEXT NOT NULL,
    tipo TEXT NOT NULL,  -- deposito | retirada
    importe DOUBLE PRECISION NOT NULL,  -- siempre positivo; el signo lo da 'tipo'
    fecha TEXT NOT NULL,
    nota TEXT,
    es_historico BOOLEAN NOT NULL DEFAULT FALSE,  -- importado de antes de llevar el bankroll: no toca el líquido
    creado_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_movimientos_bankroll_casa ON movimientos_bankroll(casa_apuestas);
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
        listar_nombres_casas.clear()
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


def reabrir_surebet(surebet_id):
    """Deshace el cierre de una surebet resuelta por error: la vuelve a
    'pendiente' y pone el resultado de todas sus patas otra vez en
    'pendiente', para poder corregirlo desde 'Registrar apuesta'."""
    with get_conn() as cur:
        cur.execute(
            "UPDATE surebets SET estado = 'pendiente', beneficio_real = NULL WHERE id = %s",
            (surebet_id,),
        )
        cur.execute(
            "UPDATE patas SET resultado = 'pendiente', importe_cierre = NULL WHERE surebet_id = %s",
            (surebet_id,),
        )
    listar_surebets_pendientes.clear()
    listar_patas.clear()
    obtener_todo_dataframe.clear()


def eliminar_surebet(surebet_id):
    with get_conn() as cur:
        cur.execute("DELETE FROM surebets WHERE id = %s", (surebet_id,))
    listar_surebets_pendientes.clear()
    listar_patas.clear()
    obtener_todo_dataframe.clear()
    listar_nombres_casas.clear()


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
    listar_nombres_casas.clear()


@st.cache_data(ttl=15)
def listar_bankroll():
    with get_conn() as cur:
        cur.execute("SELECT * FROM bankroll_casas ORDER BY casa_apuestas")
        return cur.fetchall()


def eliminar_bankroll_casa(casa_apuestas):
    with get_conn() as cur:
        cur.execute("DELETE FROM bankroll_casas WHERE casa_apuestas = %s", (casa_apuestas,))
    listar_bankroll.clear()
    listar_nombres_casas.clear()


def _ajustar_liquido(casa_apuestas, delta):
    """Suma (o resta, si delta es negativo) al líquido ya guardado de una casa,
    sin tocar lo que tenga en juego. Crea la casa si todavía no existía."""
    with get_conn() as cur:
        cur.execute(
            """INSERT INTO bankroll_casas (casa_apuestas, liquido, pendiente, actualizado_en)
               VALUES (%s, %s, 0, %s)
               ON CONFLICT (casa_apuestas) DO UPDATE
               SET liquido = bankroll_casas.liquido + EXCLUDED.liquido,
                   actualizado_en = EXCLUDED.actualizado_en""",
            (casa_apuestas, delta, _ahora()),
        )
    listar_bankroll.clear()
    listar_nombres_casas.clear()


def registrar_movimiento_bankroll(casa_apuestas, tipo, importe, fecha, nota=None, es_historico=False):
    """Registra un depósito o retirada en una casa. `importe` siempre positivo;
    el signo lo da `tipo`. Si `es_historico` es True (movimientos de antes de
    llevar el bankroll en la app), solo queda guardado como referencia y NO
    toca el líquido actual, que ya se dio de alta a mano. Si no, además ajusta
    el líquido de esa casa: un depósito lo sube, una retirada lo baja."""
    with get_conn() as cur:
        cur.execute(
            """INSERT INTO movimientos_bankroll
               (casa_apuestas, tipo, importe, fecha, nota, es_historico, creado_en)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (casa_apuestas, tipo, importe, fecha, nota, es_historico, _ahora()),
        )
        movimiento_id = cur.fetchone()["id"]
    if not es_historico:
        _ajustar_liquido(casa_apuestas, importe if tipo == "deposito" else -importe)
    listar_movimientos_bankroll.clear()
    return movimiento_id


@st.cache_data(ttl=15)
def listar_movimientos_bankroll():
    with get_conn() as cur:
        cur.execute("SELECT * FROM movimientos_bankroll ORDER BY fecha DESC, id DESC")
        return cur.fetchall()


def eliminar_movimiento_bankroll(movimiento_id):
    """Borra un movimiento y, si no era histórico, deshace su efecto sobre el
    líquido de la casa (para que borrar un depósito/retirada mal metido no
    deje el líquido descuadrado)."""
    with get_conn() as cur:
        cur.execute(
            "SELECT casa_apuestas, tipo, importe, es_historico FROM movimientos_bankroll WHERE id = %s",
            (movimiento_id,),
        )
        mov = cur.fetchone()
        cur.execute("DELETE FROM movimientos_bankroll WHERE id = %s", (movimiento_id,))
    if mov and not mov["es_historico"]:
        _ajustar_liquido(mov["casa_apuestas"], -mov["importe"] if mov["tipo"] == "deposito" else mov["importe"])
    listar_movimientos_bankroll.clear()


@st.cache_data(ttl=15)
def listar_nombres_casas():
    """Todas las casas de apuestas conocidas por la app: las que ya tienen
    líquido/en juego en el Bankroll y las que aparecen en el historial de
    apuestas, aunque todavía no se hayan añadido al Bankroll. Así, la primera
    vez que usas una casa nueva en 'Registrar apuesta' (con 'Otra...'), la
    próxima vez ya aparece en la lista sin tener que volver a escribirla."""
    with get_conn() as cur:
        cur.execute("SELECT DISTINCT casa_apuestas FROM patas")
        de_patas = {f["casa_apuestas"] for f in cur.fetchall()}
        cur.execute("SELECT casa_apuestas FROM bankroll_casas")
        de_bankroll = {f["casa_apuestas"] for f in cur.fetchall()}
    return sorted(de_patas | de_bankroll)


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
