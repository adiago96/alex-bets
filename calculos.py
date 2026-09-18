# calculos.py
"""Lógica de cálculo de surebets (arbitraje deportivo)."""

from dataclasses import dataclass


@dataclass
class ResultadoSurebet:
    es_arbitraje: bool
    probabilidad_implicita_total: float  # suma de 1/cuota, <1 => hay arbitraje
    margen_pct: float                    # beneficio garantizado en %, negativo si no hay arbitraje
    importes: list[float]                # importe a apostar en cada pata, mismo orden que las cuotas
    retorno_garantizado: float           # retorno bruto igual en cualquier resultado
    beneficio_garantizado: float         # retorno_garantizado - importe_total


def calcular_surebet(cuotas: list[float], importe_total: float) -> ResultadoSurebet:
    """Calcula el reparto de stake entre N patas para un importe total fijo.

    cuotas: cuota decimal de cada pata (ej. 2.10)
    importe_total: cantidad total de dinero a repartir entre todas las patas
    """
    if not cuotas or any(c <= 1.0 for c in cuotas):
        raise ValueError("Todas las cuotas deben ser mayores que 1.0")
    if importe_total <= 0:
        raise ValueError("El importe total debe ser mayor que 0")

    inversos = [1.0 / c for c in cuotas]
    probabilidad_implicita_total = sum(inversos)

    # Reparto proporcional al inverso de la cuota: iguala el retorno pase lo que pase.
    importes = [importe_total * inv / probabilidad_implicita_total for inv in inversos]

    # Con este reparto el retorno es el mismo para cualquier pata ganadora.
    retorno_garantizado = importes[0] * cuotas[0]
    beneficio_garantizado = retorno_garantizado - importe_total
    margen_pct = (1.0 / probabilidad_implicita_total - 1.0) * 100.0

    return ResultadoSurebet(
        es_arbitraje=probabilidad_implicita_total < 1.0,
        probabilidad_implicita_total=probabilidad_implicita_total,
        margen_pct=margen_pct,
        importes=importes,
        retorno_garantizado=retorno_garantizado,
        beneficio_garantizado=beneficio_garantizado,
    )


def calcular_importe_total_para_beneficio(cuotas: list[float], beneficio_objetivo: float) -> float:
    """Dado un beneficio garantizado deseado (en unidades monetarias), calcula
    el importe total a repartir entre las patas para lograrlo exactamente."""
    if not cuotas or any(c <= 1.0 for c in cuotas):
        raise ValueError("Todas las cuotas deben ser mayores que 1.0")

    probabilidad_implicita_total = sum(1.0 / c for c in cuotas)
    if probabilidad_implicita_total >= 1.0:
        raise ValueError("Estas cuotas no forman una surebet (no hay beneficio posible)")

    margen = 1.0 / probabilidad_implicita_total - 1.0
    return beneficio_objetivo / margen


def calcular_resultado_real(patas_importes_cuotas_resultado: list[tuple[float, float, str]], importe_total: float) -> float:
    """Calcula el beneficio real una vez resueltas todas las patas.

    patas_importes_cuotas_resultado: lista de tuplas (importe, cuota, resultado)
    donde resultado es 'ganada' o 'perdida'.
    """
    retorno = 0.0
    for importe, cuota, resultado in patas_importes_cuotas_resultado:
        if resultado == "ganada":
            retorno += importe * cuota
    return retorno - importe_total
