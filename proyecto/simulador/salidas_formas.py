"""Salidas nuevas del documento 5, en matrices SL × TP, con cierre por minutos desde la entrada.

Mismas reglas que `salidas`: TP al pasar 2 ticks, stops con −2 ticks (al precio del stop si
`salidas.SL_AL_PRECIO`), cierre por tiempo con el primer tick en o después del plazo, −2 ticks.
"""

import numpy as np

from simulador import salidas
from simulador.operaciones import Operacion

_D = salidas._DESLIZ
GRID = salidas.GRID


def _stop_en_nivel(op: Operacion, indice: int, nivel: float) -> float:
    return nivel - _D if salidas.SL_AL_PRECIO else float(op.favor[min(indice, len(op.favor) - 1)] - _D)


def condicional(op: Operacion, minutos: float, extra: float, sl=GRID, tp=GRID) -> tuple[np.ndarray, np.ndarray]:
    """A los X minutos: si va perdiendo o en cero, se cierra; si va ganando, SL a la entrada y `extra` minutos más."""
    a, b = salidas._primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    valor, indice = salidas._combinar(op, c, a[:, None], b[None, :], tp, salidas._stop_fijo(op, a, sl)[:, None])
    if op.favor[c] <= 0:
        return valor, indice
    c2 = op.cierre_minutos(minutos + extra)
    vuelta = salidas._vuelta_a_entrada(op, c)
    sigue = (np.minimum(a[:, None], b[None, :]) >= c)  # no salió antes del plazo
    tp_luego = sigue & (b[None, :] < min(vuelta, c2))
    be = sigue & ~tp_luego & (vuelta < c2)
    tiempo2 = sigue & ~tp_luego & ~be
    valor = np.where(tp_luego, tp[None, :], np.where(be, _stop_en_nivel(op, vuelta, 0), np.where(tiempo2, int(op.favor[c2]) - _D, valor)))
    indice = np.where(tp_luego, b[None, :], np.where(be, vuelta, np.where(tiempo2, c2, indice)))
    return valor, indice


def corte_temprano(op: Operacion, minutos: float, revisa: float, umbral: int, sl=GRID, tp=GRID) -> tuple[np.ndarray, np.ndarray]:
    """Si a los `revisa` minutos va `umbral` ticks o más en contra, se sale a mercado."""
    a, b = salidas._primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    valor, indice = salidas._combinar(op, c, a[:, None], b[None, :], tp, salidas._stop_fijo(op, a, sl)[:, None])
    r = op.cierre_minutos(revisa)
    if r >= c or op.favor[r] > -umbral:
        return valor, indice
    corta = np.minimum(a[:, None], b[None, :]) >= r
    return np.where(corta, int(op.favor[r]) - _D, valor), np.where(corta, r, indice)


def trailing_velas(op: Operacion, minutos: float, sl=GRID, tp=GRID) -> tuple[np.ndarray, np.ndarray]:
    """Tras cada vela que cierra a favor, el SL sube al mínimo (Buy) o baja al máximo (Sell) de esa vela."""
    _, b = salidas._primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    n = len(op.favor)
    a = np.full(len(sl), n, dtype=np.int64)
    nivel_salida = np.zeros(len(sl))
    rastro = -np.inf
    ini = 0
    for fin in [int(x) for x in op.cierres if int(x) < c] + [c]:
        if fin > ini:
            niveles = np.maximum(-sl.astype(float), rastro)
            peor = np.minimum.accumulate(op.favor[ini:fin])
            pos = np.searchsorted(-peor, -niveles, side="left")
            nuevo = (pos < fin - ini) & (a == n)
            a = np.where(nuevo, ini + pos, a)
            nivel_salida = np.where(nuevo, niveles, nivel_salida)
            if op.favor[fin - 1] > 0:
                rastro = max(rastro, float(op.favor[ini:fin].min()))
        ini = fin
    valor_stop = (nivel_salida - _D) if salidas.SL_AL_PRECIO else salidas._valor_en(op, a)
    return salidas._combinar(op, c, a[:, None], b[None, :], tp, valor_stop[:, None])


def contraria(op: Operacion, minutos: float, indice_contraria: int | None, sl=GRID, tp=GRID) -> tuple[np.ndarray, np.ndarray]:
    """Se sale a mercado cuando confirma una señal contraria de tu registro (si llega antes del cierre)."""
    a, b = salidas._primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    if indice_contraria is not None and indice_contraria < c:
        c = indice_contraria
    return salidas._combinar(op, c, a[:, None], b[None, :], tp, salidas._stop_fijo(op, a, sl)[:, None])


def tp_proporcional(op: Operacion, minutos: float, atr: float, factores: np.ndarray, sl=GRID) -> tuple[np.ndarray, np.ndarray]:
    """SL fijo (cuadrícula) y TP = factor × ATR de la señal (en ticks)."""
    tp = np.maximum(np.floor(factores * atr + 0.5).astype(np.int64), 4)
    a, b = salidas._primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    return salidas._combinar(op, c, a[:, None], b[None, :], tp, salidas._stop_fijo(op, a, sl)[:, None])
