# telegram_parser.py
"""Interpreta los mensajes de oportunidades ('sures') del canal de Telegram.

El texto de cada mensaje (sin contar el nombre del canal, que Telegram
muestra en la interfaz pero no forma parte del texto del mensaje) siempre
tiene este formato:

    📈 ROI 2.21%
    🏆 EFL Championship
    ⚽ Bristol City vs Watford
    ⏱️ Comienza en: 5h 37m

    🏠 Leovegas
    🎯 Tiros del equipo - Watford + 11.5
    💵 Cuota @2.2

    🏠 Bet365
    🎯 Tiros del equipo - Watford - 11.5
    💵 Cuota @1.909

    🔎 Consejo: ...

El emoji del deporte (⚽, 🏀, ...) y el número de patas pueden variar, pero
el resto de marcadores (📈 🏆 ⏱️ 🏠 🎯 💵) son siempre los mismos.
"""

import re
from dataclasses import dataclass
from datetime import timedelta


@dataclass
class PataOportunidad:
    casa_apuestas: str
    seleccion: str
    cuota: float


@dataclass
class OportunidadSure:
    roi_pct: float
    torneo: str
    evento: str
    comienza_en: str
    patas: list[PataOportunidad]
    texto_original: str


_RE_ROI = re.compile(r"📈\s*ROI\s*([\d.,]+)\s*%")
_RE_TORNEO = re.compile(r"🏆\s*(.+)")
_RE_EVENTO_LINEA = re.compile(r"^(.+\svs\s.+)$", re.MULTILINE)
_RE_COMIENZA = re.compile(r"⏱️?\s*Comienza en:\s*(.+)")
_RE_PATA = re.compile(
    r"🏠\s*(?P<casa>.+?)\s*\n"
    r"🎯\s*(?P<seleccion>.+?)\s*\n"
    r"💵\s*Cuota\s*@\s*(?P<cuota>[\d.,]+)"
)
_RE_DURACION = re.compile(r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", re.IGNORECASE)


def calcular_duracion(comienza_en: str) -> timedelta | None:
    """Convierte el texto de 'Comienza en: ...' (ej. '5h 37m') en un
    timedelta. Devuelve None si no reconoce ningún número (para no asumir
    una duración incorrecta)."""
    match = _RE_DURACION.search(comienza_en or "")
    if not match or not any(match.groups()):
        return None
    dias, horas, minutos = (int(g) if g else 0 for g in match.groups())
    return timedelta(days=dias, hours=horas, minutes=minutos)


def parsear_mensaje_sure(texto: str) -> OportunidadSure | None:
    """Convierte el texto de un mensaje del canal en una `OportunidadSure`.

    Devuelve None si el texto no tiene la estructura esperada (por ejemplo,
    un mensaje informativo del canal que no es una oportunidad).
    """
    if not texto:
        return None

    roi_match = _RE_ROI.search(texto)
    evento_match = _RE_EVENTO_LINEA.search(texto)
    patas = [
        PataOportunidad(
            casa_apuestas=m.group("casa").strip(),
            seleccion=m.group("seleccion").strip(),
            cuota=float(m.group("cuota").replace(",", ".")),
        )
        for m in _RE_PATA.finditer(texto)
    ]

    if not roi_match or not evento_match or len(patas) < 2:
        return None

    torneo_match = _RE_TORNEO.search(texto)
    comienza_match = _RE_COMIENZA.search(texto)

    evento_linea = evento_match.group(1).strip()
    evento = re.sub(r"^\S+\s+", "", evento_linea)  # quita el emoji del deporte al principio

    return OportunidadSure(
        roi_pct=float(roi_match.group(1).replace(",", ".")),
        torneo=torneo_match.group(1).strip() if torneo_match else "",
        evento=evento,
        comienza_en=comienza_match.group(1).strip() if comienza_match else "",
        patas=patas,
        texto_original=texto,
    )
