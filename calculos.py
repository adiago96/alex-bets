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


def _claves_de_grupo(selecciones: list[str]) -> list[str]:
    """Clave de agrupación por selección: dos patas con la misma selección (texto)
    representan el mismo resultado real (p.ej. la misma apuesta repartida entre dos
    casas porque una de ellas limita el importe). Las patas sin selección todavía
    rellenada no se agrupan entre sí."""
    return [sel if sel else f"__sin_seleccion_{i}__" for i, sel in enumerate(selecciones)]


def _cuotas_efectivas_por_grupo(selecciones: list[str], cuotas: list[float]):
    """Para cada grupo (selección), se queda con el índice de la pata con mejor
    cuota: es la que debería absorber todo el importe salvo que esté limitada.
    Devuelve (claves_unicas, cuotas_unicas_en_ese_orden, representante_por_clave)."""
    claves = _claves_de_grupo(selecciones)
    representante: dict[str, int] = {}
    for i, (clave, cuota) in enumerate(zip(claves, cuotas)):
        if clave not in representante or cuota > cuotas[representante[clave]]:
            representante[clave] = i
    claves_unicas = list(representante.keys())
    cuotas_unicas = [cuotas[representante[clave]] for clave in claves_unicas]
    return claves, claves_unicas, cuotas_unicas, representante


def calcular_sugerencia_agrupada(selecciones: list[str], cuotas: list[float], importe_total: float) -> list[float]:
    """Sugerencia de importe por pata cuando puede haber varias patas para la
    misma selección (repartida entre casas por límite de importe). Dentro de
    cada grupo, la sugerencia pone todo el importe en la pata de mejor cuota y
    0 € en las demás (solo hace falta usarlas si la primera casa te limita)."""
    claves, claves_unicas, cuotas_unicas, representante = _cuotas_efectivas_por_grupo(selecciones, cuotas)
    resultado = calcular_surebet(cuotas_unicas, importe_total)
    importe_por_clave = dict(zip(claves_unicas, resultado.importes))
    return [
        importe_por_clave[clave] if i == representante[clave] else 0.0
        for i, clave in enumerate(claves)
    ]


def calcular_importe_total_para_beneficio_agrupado(
    selecciones: list[str], cuotas: list[float], beneficio_objetivo: float
) -> float:
    """Igual que calcular_importe_total_para_beneficio pero agrupando antes las
    patas que comparten selección (ver calcular_sugerencia_agrupada)."""
    _, _, cuotas_unicas, _ = _cuotas_efectivas_por_grupo(selecciones, cuotas)
    return calcular_importe_total_para_beneficio(cuotas_unicas, beneficio_objetivo)


def calcular_reparto_desde_grupo_fijo(
    selecciones: list[str], cuotas: list[float], importes_actuales: list[float], indice_referencia: int
) -> list[float | None]:
    """El grupo (selección) de `indice_referencia` se trata como fijado a mano:
    se suma lo que ya llevan repartido sus patas (p.ej. una casa limitada más lo
    que se le añade en otra) y se usa ese retorno como objetivo para calcular el
    importe de la pata de mejor cuota de cada uno de los demás grupos. Las patas
    del propio grupo de referencia devuelven None (no hay sugerencia para ellas,
    se rellenan a mano)."""
    if not cuotas or any(c <= 1.0 for c in cuotas):
        raise ValueError("Todas las cuotas deben ser mayores que 1.0")

    claves = _claves_de_grupo(selecciones)
    clave_ref = claves[indice_referencia]
    retorno_ref = sum(
        importe * cuota
        for clave, cuota, importe in zip(claves, cuotas, importes_actuales)
        if clave == clave_ref
    )
    if retorno_ref <= 0:
        raise ValueError("Introduce primero el importe en la(s) pata(s) de referencia")

    _, _, _, representante = _cuotas_efectivas_por_grupo(selecciones, cuotas)
    resultado: list[float | None] = []
    for i, clave in enumerate(claves):
        if clave == clave_ref:
            resultado.append(None)
        elif i == representante[clave]:
            resultado.append(retorno_ref / cuotas[i])
        else:
            resultado.append(0.0)
    return resultado


def calcular_beneficios_por_seleccion(
    selecciones: list[str], cuotas: list[float], importes: list[float]
) -> list[float]:
    """Beneficio si gana cada pata, agrupando antes las patas que comparten
    selección: si dos patas apuestan al mismo resultado (repartido entre dos
    casas), ganan o pierden juntas, así que su beneficio debe sumar ambos
    retornos, no calcularse como si fueran resultados independientes."""
    claves = _claves_de_grupo(selecciones)
    importe_total = sum(importes)
    retorno_por_clave: dict[str, float] = {}
    for clave, cuota, importe in zip(claves, cuotas, importes):
        retorno_por_clave[clave] = retorno_por_clave.get(clave, 0.0) + importe * cuota
    return [retorno_por_clave[clave] - importe_total for clave in claves]


def calcular_resultado_real(patas_importes_cuotas_resultado: list[tuple[float, float, str]], importe_total: float) -> float:
    """Calcula el beneficio real una vez resueltas todas las patas.

    patas_importes_cuotas_resultado: lista de tuplas (importe, cuota, resultado)
    donde resultado es 'ganada', 'perdida' o 'anulada'. Una pata anulada
    devuelve el importe apostado (no se gana ni se pierde esa parte del stake).
    """
    retorno = 0.0
    for importe, cuota, resultado in patas_importes_cuotas_resultado:
        if resultado == "ganada":
            retorno += importe * cuota
        elif resultado == "anulada":
            retorno += importe
    return retorno - importe_total
