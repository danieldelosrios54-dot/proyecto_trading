"""Reglas del día sobre una forma de operar ya elegida: límites, máximo de operaciones, horarios y zonas.

Recorre las operaciones por hora de entrada, respeta el solapamiento y reinicia el estado cada día.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass
class EstadoDia:
    operaciones: int = 0
    perdidas_seguidas: int = 0
    neto: float = 0.0


Regla = Callable[[int, EstadoDia], bool]  # (operación, estado del día) -> ¿se toma?


def aplicar(valores: np.ndarray, entrada_ns: np.ndarray, salida_ns: np.ndarray, dia: np.ndarray, regla: Regla | None) -> np.ndarray:
    """Índices de las operaciones tomadas."""
    tomadas = []
    libre = np.iinfo(np.int64).min
    dia_actual, estado = None, EstadoDia()
    for k in np.argsort(entrada_ns, kind="stable"):
        if entrada_ns[k] < libre:
            continue
        if dia[k] != dia_actual:
            dia_actual, estado = dia[k], EstadoDia()
        if regla is not None and not regla(int(k), estado):
            continue
        tomadas.append(int(k))
        libre = salida_ns[k]
        estado.operaciones += 1
        estado.neto += float(valores[k])
        estado.perdidas_seguidas = estado.perdidas_seguidas + 1 if valores[k] < 0 else 0
    return np.array(tomadas, dtype=np.int64)


def reglas(minutos: np.ndarray, zona: np.ndarray, zonas: list[str], config_reglas) -> dict[str, Regla]:
    """Catálogo de reglas, cada una por separado frente a la base."""
    c = config_reglas
    catalogo: dict[str, Regla] = {"Base (sin reglas del día)": lambda k, e: True}
    for usd in c.REGLA_PERDIDA_USD:
        catalogo[f"Dejar de operar al perder {usd} USD en el día"] = lambda k, e, u=usd: e.neto > -u
    for usd in c.REGLA_GANANCIA_USD:
        catalogo[f"Dejar de operar al ganar {usd} USD en el día"] = lambda k, e, u=usd: e.neto < u
    for n in c.REGLA_MAX_OPERACIONES:
        catalogo[f"Máximo {n} operaciones por día"] = lambda k, e, n=n: e.operaciones < n
    for n in c.REGLA_PERDIDAS_SEGUIDAS:
        catalogo[f"Dejar de operar tras {n} pérdida(s) seguida(s)"] = lambda k, e, n=n: e.perdidas_seguidas < n
    for desde, hasta in c.REGLA_HORARIOS_MIN:
        catalogo[f"Solo de minuto {desde} a {hasta} desde la apertura"] = lambda k, e, a=desde, b=hasta: a <= minutos[k] < b
    for i, nombre in enumerate(zonas):
        catalogo[f"Dejar de operar {nombre}"] = lambda k, e, i=i: zona[k] != i
    return catalogo
