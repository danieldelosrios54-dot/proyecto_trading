"""Qué señales se toman cuando pueden coincidir varias operaciones, para cada combinación SL/TP.

NinjaTrader compensa compra y venta en la misma cuenta: solo se permiten varias posiciones a la vez
en la misma dirección; una señal contraria se pierde mientras haya alguna abierta.
"""

import numpy as np


def tomar(
    entrada_ns: np.ndarray, salida_ns: np.ndarray, signo: np.ndarray,
    maximo: int = 1, orden: np.ndarray | None = None, separacion_ns: int = 0,
) -> np.ndarray:
    """Matriz (operaciones × combinaciones) de las operaciones tomadas.

    maximo: posiciones abiertas a la vez en la misma dirección (1 = solapamiento actual).
    orden: orden de recorrido; por defecto, hora de entrada y luego posición en el registro.
    separacion_ns: tiempo mínimo desde la entrada de la última operación tomada.
    """
    n, c = salida_ns.shape
    orden = np.argsort(entrada_ns, kind="stable") if orden is None else orden
    abiertas = np.full((maximo, c), np.iinfo(np.int64).min, dtype=np.int64)
    direccion = np.zeros(c, dtype=np.int64)
    ultima = np.full(c, np.iinfo(np.int64).min // 2, dtype=np.int64)
    tomada = np.zeros((n, c), dtype=bool)
    columnas = np.arange(c)
    for k in orden:
        t = entrada_ns[k]
        activas = abiertas > t
        cuantas = activas.sum(0)
        misma = (cuantas == 0) | (direccion == signo[k])
        entra = misma & (cuantas < maximo) & (t >= ultima + separacion_ns)
        hueco = np.argmin(activas, axis=0)
        abiertas[hueco[entra], columnas[entra]] = salida_ns[k, entra]
        direccion = np.where(entra, signo[k], direccion)
        ultima = np.where(entra, t, ultima)
        tomada[k] = entra
    return tomada


def orden_con_prioridad(entrada_ns: np.ndarray, prioridad: np.ndarray) -> np.ndarray:
    """Recorre por hora de entrada; si dos entran en el mismo instante, primero la de menor `prioridad`."""
    return np.lexsort((prioridad, entrada_ns))
