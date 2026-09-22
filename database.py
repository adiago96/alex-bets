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

CREATE TABLE IF NOT EXISTS oportunidades (
    id SERIAL PRIMARY KEY,
    recibido_en TEXT NOT NULL,
    roi_pct DOUBLE PRECISION NOT NULL,
    torneo TEXT NOT NULL,
    evento TEXT NOT NULL,
    comienza_en TEXT NOT NULL,   -- texto original del canal, ej. "5h 37m" (solo informativo)
    empieza_en TEXT,             -- fecha/hora absoluta calculada al recibir el mensaje, para filtrar
    texto_original TEXT NOT NULL,
    firma TEXT NOT NULL,         -- evento + casas/selecciones, para detectar duplicados
    usada INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oportunidad_patas (
    id SERIAL PRIMARY KEY,
    oportunidad_id INTEGER NOT NULL REFERENCES oportunidades(id) ON DELETE CASCADE,
    casa_apuestas TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    cuota DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oportunidad_patas_oportunidad ON oportunidad_patas(oportunidad_id);
CREATE INDEX IF NOT EXISTS idx_oportunidades_usada ON oportunidades(usada);
CREATE INDEX IF NOT EXISTS idx_oportunidades_firma ON oportunidades(firma);

-- Fila unica con el estado de la sincronizacion bajo demanda con Telegram
-- (evita que dos pestañas/dispositivos abiertos a la vez disparen la
-- sincronizacion en el mismo minuto).
CREATE TABLE IF NOT EXISTS sync_estado (
    id INTEGER PRIMARY KEY DEFAULT 1,
    ultima_sincronizacion TEXT,
    CONSTRAINT sync_estado_una_fila CHECK (id = 1)
);
"""

_pool = None


def _connection_string() -> str:
    try:
        import streamlit as st
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
        cur.execute(
            "INSERT INTO sync_estado (id, ultima_sincronizacion) VALUES (1, NULL) "
            "ON CONFLICT (id) DO NOTHING"
        )


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
        return surebet_id


def listar_surebets_pendientes():
    with get_conn() as cur:
        cur.execute("SELECT * FROM surebets WHERE estado = 'pendiente' ORDER BY fecha DESC, id DESC")
        return cur.fetchall()


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


def cerrar_surebet(surebet_id, beneficio_real):
    with get_conn() as cur:
        cur.execute(
            "UPDATE surebets SET estado = 'resuelta', beneficio_real = %s WHERE id = %s",
            (beneficio_real, surebet_id),
        )


def eliminar_surebet(surebet_id):
    with get_conn() as cur:
        cur.execute("DELETE FROM surebets WHERE id = %s", (surebet_id,))


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
    ahora = _ahora()
    with get_conn() as cur:
        cur.execute(
            """SELECT id FROM oportunidades
               WHERE firma = %s AND (empieza_en IS NULL OR empieza_en > %s)""",
            (firma, ahora),
        )
        existente = cur.fetchone()

        if existente:
            oportunidad_id = existente["id"]
            cur.execute(
                """UPDATE oportunidades
                   SET roi_pct = %s, torneo = %s, comienza_en = %s, empieza_en = %s,
                       texto_original = %s, recibido_en = %s
                   WHERE id = %s""",
                (roi_pct, torneo, comienza_en, empieza_en, texto_original, ahora, oportunidad_id),
            )
            cur.execute("DELETE FROM oportunidad_patas WHERE oportunidad_id = %s", (oportunidad_id,))
        else:
            cur.execute(
                """INSERT INTO oportunidades
                   (recibido_en, roi_pct, torneo, evento, comienza_en, empieza_en, texto_original, firma)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (ahora, roi_pct, torneo, evento, comienza_en, empieza_en, texto_original, firma),
            )
            oportunidad_id = cur.fetchone()["id"]

        cur.executemany(
            """INSERT INTO oportunidad_patas (oportunidad_id, casa_apuestas, seleccion, cuota)
               VALUES (%s, %s, %s, %s)""",
            [(oportunidad_id, p["casa_apuestas"], p["seleccion"], p["cuota"]) for p in patas],
        )
        return oportunidad_id


def eliminar_oportunidades_caducadas():
    """Borra las oportunidades cuyo evento ya ha empezado (según empieza_en)."""
    with get_conn() as cur:
        cur.execute(
            "DELETE FROM oportunidades WHERE empieza_en IS NOT NULL AND empieza_en <= %s", (_ahora(),)
        )


def listar_oportunidades(solo_no_usadas=True, limite=50):
    """Lista oportunidades cuyo evento todavía no ha empezado (o sin hora
    reconocida), más recientes primero por hora de inicio."""
    with get_conn() as cur:
        condiciones = ["(empieza_en IS NULL OR empieza_en > %s)"]
        parametros = [_ahora()]
        if solo_no_usadas:
            condiciones.append("usada = 0")
        query = (
            "SELECT * FROM oportunidades WHERE " + " AND ".join(condiciones)
            + " ORDER BY empieza_en IS NULL, empieza_en ASC LIMIT %s"
        )
        parametros.append(limite)
        cur.execute(query, parametros)
        return cur.fetchall()


def listar_oportunidad_patas(oportunidad_id):
    with get_conn() as cur:
        cur.execute(
            "SELECT * FROM oportunidad_patas WHERE oportunidad_id = %s ORDER BY id", (oportunidad_id,)
        )
        return cur.fetchall()


def marcar_oportunidad_usada(oportunidad_id):
    with get_conn() as cur:
        cur.execute("UPDATE oportunidades SET usada = 1 WHERE id = %s", (oportunidad_id,))


def eliminar_oportunidad(oportunidad_id):
    with get_conn() as cur:
        cur.execute("DELETE FROM oportunidades WHERE id = %s", (oportunidad_id,))


def debe_sincronizar_oportunidades(cooldown_segundos=60):
    """Comprueba si ha pasado el tiempo de espera desde la última sincronización
    con Telegram y, si es así, marca ahora mismo como la nueva última vez (para
    que si abres la app desde dos sitios a la vez no se dispare dos veces
    seguidas). Devuelve True si toca sincronizar."""
    ahora = datetime.now()
    with get_conn() as cur:
        cur.execute("SELECT ultima_sincronizacion FROM sync_estado WHERE id = 1")
        fila = cur.fetchone()
        ultima = fila["ultima_sincronizacion"] if fila else None
        if ultima:
            transcurrido = (ahora - datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S")).total_seconds()
            if transcurrido < cooldown_segundos:
                return False
        cur.execute(
            "UPDATE sync_estado SET ultima_sincronizacion = %s WHERE id = 1",
            (ahora.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        return True


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
