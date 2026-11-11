"""Resultado de una operación con cada forma de salida.

Todas devuelven ticks a favor de la salida (sin comisión) y el índice del tick que cierra.
Reglas: TP exige pasar TP + 2 ticks y sale al precio TP; SL, breakeven y cierres por tiempo
salen al precio del tick que los dispara − 2 ticks; el cierre por tiempo usa el primer tick
en o tras el cierre de la vela K.
"""

import numpy as np

import config
from simulador.operaciones import Operacion

GRID = np.array(config.SIM_TICKS, dtype=np.int64)
_EXCESO = config.TP_EXCESO_TICKS
_DESLIZ = config.SALIDA_DESLIZ_TICKS

# Con True, toda salida por stop (SL, breakeven, trailing) registra el precio del stop − 2 ticks,
# como en el entregable principal. Con False, el precio del tick que lo dispara − 2 (simulador anterior).
SL_AL_PRECIO = False


def usd(ticks: np.ndarray | float) -> np.ndarray | float:
    return ticks * config.USD_POR_TICK - config.COMISION_USD


def _primeros(op: Operacion, sl: np.ndarray, tp: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Primer índice en que se toca cada SL y cada TP (len si nunca)."""
    return np.searchsorted(op.contra, sl, side="left"), np.searchsorted(op.maximo, tp + _EXCESO, side="left")


def _valor_en(op: Operacion, indices: np.ndarray) -> np.ndarray:
    return op.favor[np.minimum(indices, len(op.favor) - 1)] - _DESLIZ


def _stop_fijo(op: Operacion, a: np.ndarray, sl: np.ndarray) -> np.ndarray:
    return (-sl - _DESLIZ) if SL_AL_PRECIO else _valor_en(op, a)


def _combinar(op: Operacion, c: int, a: np.ndarray, b: np.ndarray, tp: np.ndarray, valor_stop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """a y valor_stop en columna (SL), b en fila (TP). Gana lo que ocurra primero antes del cierre."""
    tiempo = int(op.favor[c]) - _DESLIZ
    gana_tp = (b < a) & (b < c)
    stop = ~gana_tp & (a < c)
    valor = np.where(gana_tp, tp[None, :], np.where(stop, valor_stop, tiempo))
    indice = np.where(gana_tp, b, np.where(stop, a, c))
    return valor, indice


def fijo(op: Operacion, velas: int, sl: np.ndarray = GRID, tp: np.ndarray = GRID) -> tuple[np.ndarray, np.ndarray]:
    """Matrices SL × TP."""
    a, b = _primeros(op, sl, tp)
    c = op.cierre(velas)
    return _combinar(op, c, a[:, None], b[None, :], tp, _stop_fijo(op, a, sl)[:, None])


def fijo_minutos(op: Operacion, minutos: float, sl: np.ndarray = GRID, tp: np.ndarray = GRID) -> tuple[np.ndarray, np.ndarray]:
    """Matrices SL × TP con cierre a X minutos desde la entrada y salida del SL al precio del SL − 2 ticks."""
    a, b = _primeros(op, sl, tp)
    c = op.cierre_minutos(minutos)
    return _combinar(op, c, a[:, None], b[None, :], tp, (-sl - _DESLIZ)[:, None])


def _vuelta_a_entrada(op: Operacion, desde: int) -> int:
    """Primer índice desde `desde` con el precio en la entrada o peor."""
    if desde >= len(op.favor):
        return len(op.favor)
    vuelve = np.flatnonzero(op.favor[desde:] <= 0)
    return desde + int(vuelve[0]) if vuelve.size else len(op.favor)


def breakeven(op: Operacion, velas: int, nivel: int, sl: np.ndarray = GRID, tp: np.ndarray = GRID) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Al llegar a +nivel, el SL pasa al precio de entrada. Devuelve también qué celdas cerraron en breakeven."""
    a, b = _primeros(op, sl, tp)
    c = op.cierre(velas)
    valor, indice = _combinar(op, c, a[:, None], b[None, :], tp, _stop_fijo(op, a, sl)[:, None])
    activa = int(np.searchsorted(op.maximo, nivel, side="left"))
    vuelta = _vuelta_a_entrada(op, activa)
    a_c, b_f = a[:, None], b[None, :]
    con_be = (activa < np.minimum(a_c, b_f)) & (activa < c)
    cierra_be = con_be & (vuelta < b_f) & (vuelta < c)
    tp_tras_be = con_be & (b_f < vuelta) & (b_f < c)
    tiempo = int(op.favor[c]) - _DESLIZ
    valor_vuelta = -_DESLIZ if SL_AL_PRECIO else int(op.favor[min(vuelta, len(op.favor) - 1)]) - _DESLIZ
    valor_be = np.where(cierra_be, valor_vuelta, np.where(tp_tras_be, tp[None, :], tiempo))
    indice_be = np.where(cierra_be, vuelta, np.where(tp_tras_be, b_f, c))
    return np.where(con_be, valor_be, valor), np.where(con_be, indice_be, indice), cierra_be


def niveles_sl_tiempo(sl: np.ndarray, velas: int, cerradas: int) -> np.ndarray:
    """SL vigente tras `cerradas` velas cerradas: se acerca por partes iguales hasta el cierre."""
    return np.maximum(np.floor(sl * (velas - cerradas) / velas + 0.5).astype(np.int64), 1)


def sl_tiempo(op: Operacion, velas: int, sl: np.ndarray = GRID, tp: np.ndarray = GRID) -> tuple[np.ndarray, np.ndarray]:
    """El SL se acerca al cerrar cada vela: con SL 180 y 6 velas pasa a 150, 120, 90, 60 y 30."""
    _, b = _primeros(op, sl, tp)
    c = op.cierre(velas)
    n = op.velas_hasta_cierre(velas)
    a = np.full(len(sl), len(op.favor), dtype=np.int64)
    nivel = np.zeros(len(sl), dtype=np.int64)
    for cerradas in range(n):
        ini = 0 if cerradas == 0 else int(op.cierres[cerradas - 1])
        fin = int(op.cierres[cerradas])
        if fin <= ini:
            continue
        peor = -np.minimum.accumulate(op.favor[ini:fin])
        niveles = niveles_sl_tiempo(sl, n, cerradas)
        pos = np.searchsorted(peor, niveles, side="left")
        nuevo = (pos < fin - ini) & (a == len(op.favor))
        a = np.where(nuevo, ini + pos, a)
        nivel = np.where(nuevo, niveles, nivel)
    valor_stop = (-nivel - _DESLIZ) if SL_AL_PRECIO else _valor_en(op, a)
    return _combinar(op, c, a[:, None], b[None, :], tp, valor_stop[:, None])


# ---- Otras salidas, con parámetros gruesos -------------------------------------------------

def _primer(arr: np.ndarray, umbral: float) -> int:
    return int(np.searchsorted(arr, umbral, side="left"))


def _stop_o_tiempo(op: Operacion, a: int, c: int, nivel: float | None = None) -> tuple[float, int]:
    """`nivel`: precio del stop en ticks a favor (negativo para un SL); se usa si SL_AL_PRECIO."""
    if a < c:
        if SL_AL_PRECIO and nivel is not None:
            return float(nivel - _DESLIZ), a
        return float(op.favor[a] - _DESLIZ), a
    return float(op.favor[c] - _DESLIZ), c


def parcial(op: Operacion, velas: int) -> tuple[list[float], list[int], list[str]]:
    """Dos contratos: uno sale en TP1; el otro en TP2, con el SL igual o en breakeven. Ticks por contrato."""
    c = op.cierre(velas)
    valores, indices, nombres = [], [], []
    for sl in config.OTRAS_SL:
        a = _primer(op.contra, sl)
        for tp1 in config.PARCIAL_TP1:
            b1 = _primer(op.maximo, tp1 + _EXCESO)
            vuelta = _vuelta_a_entrada(op, b1)
            for tp2 in config.PARCIAL_TP2:
                b2 = _primer(op.maximo, tp2 + _EXCESO)
                for modo in ("SL igual", "breakeven"):
                    if b1 < a and b1 < c:
                        j = vuelta if modo == "breakeven" else a
                        if b2 < j and b2 < c:
                            segundo, q = float(tp2), b2
                        else:
                            segundo, q = _stop_o_tiempo(op, j, c, 0 if modo == "breakeven" else -sl)
                        valor = (tp1 + segundo) / 2
                    else:
                        valor, q = _stop_o_tiempo(op, a, c, -sl)
                    valores.append(valor)
                    indices.append(q)
                    nombres.append(f"SL {sl} · TP1 {tp1} · TP2 {tp2} · {modo}")
    return valores, indices, nombres


def trailing(op: Operacion, velas: int) -> tuple[list[float], list[int], list[str]]:
    """Sin TP: al llegar a +activa, el SL sigue al mejor precio a `distancia` ticks."""
    c = op.cierre(velas)
    valores, indices, nombres = [], [], []
    for sl in config.OTRAS_SL:
        a = _primer(op.contra, sl)
        for activa in config.TRAILING_ACTIVA:
            ia = _primer(op.maximo, activa)
            for distancia in config.TRAILING_DISTANCIA:
                t = len(op.favor)
                if ia < len(op.favor):
                    toca = np.flatnonzero(op.favor[ia:] <= op.maximo[ia:] - distancia)
                    t = ia + int(toca[0]) if toca.size else t
                nivel = float(op.maximo[t] - distancia) if t < a and t < len(op.favor) else -sl
                valor, q = _stop_o_tiempo(op, min(a, t), c, nivel)
                valores.append(valor)
                indices.append(q)
                nombres.append(f"SL {sl} · activa +{activa} · distancia {distancia}")
    return valores, indices, nombres


def cierre_de_vela(op: Operacion, velas: int) -> tuple[list[float], list[int], list[str]]:
    """El SL solo se mira al cierre de cada vela; un stop de catástrofe protege dentro de la vela."""
    c = op.cierre(velas)
    valores, indices, nombres = [], [], []
    cierres_previos = [int(op.cierres[j - 1]) for j in range(1, op.velas_hasta_cierre(velas)) if int(op.cierres[j - 1]) < c]
    for stop in config.CIERRE_VELA_STOP:
        salida_vela = next((q for q in cierres_previos if op.favor[q - 1] <= -stop), len(op.favor))
        for catastrofe in config.CIERRE_VELA_CATASTROFE:
            a = _primer(op.contra, catastrofe)
            for tp in (*config.OTRAS_TP, None):
                b = _primer(op.maximo, tp + _EXCESO) if tp is not None else len(op.favor)
                primero = min(a, b, salida_vela)
                if primero >= c:
                    valor, q = float(op.favor[c] - _DESLIZ), c
                elif primero == b:
                    valor, q = float(tp), b
                elif primero == a and SL_AL_PRECIO:
                    valor, q = float(-catastrofe - _DESLIZ), primero
                else:
                    valor, q = float(op.favor[primero] - _DESLIZ), primero
                valores.append(valor)
                indices.append(q)
                nombres.append(f"cierre bajo −{stop} · catástrofe {catastrofe} · TP {tp if tp else 'sin TP'}")
    return valores, indices, nombres


def sin_reaccion(op: Operacion, velas: int) -> tuple[list[float], list[int], list[str]]:
    """Si al cerrar la vela N no llegó a +mínimo, se sale."""
    c = op.cierre(velas)
    valores, indices, nombres = [], [], []
    for sl in config.REACCION_SL:
        a = _primer(op.contra, sl)
        for tp in config.REACCION_TP:
            b = _primer(op.maximo, tp + _EXCESO)
            for vela in config.REACCION_VELA:
                if vela >= op.velas_hasta_cierre(velas):
                    continue
                q_vela = int(op.cierres[vela - 1])
                for minimo in config.REACCION_MINIMO:
                    salir = op.maximo[q_vela - 1] < minimo and min(a, b) >= q_vela
                    if salir:
                        valor, q = float(op.favor[q_vela] - _DESLIZ), q_vela
                    elif b < a and b < c:
                        valor, q = float(tp), b
                    else:
                        valor, q = _stop_o_tiempo(op, a, c, -sl)
                    valores.append(valor)
                    indices.append(q)
                    nombres.append(f"SL {sl} · TP {tp} · revisa vela {vela} · mínimo +{minimo}")
    return valores, indices, nombres


def fijo_grueso(op: Operacion, velas: int) -> tuple[list[float], list[int], list[str]]:
    """SL/TP fijos con los mismos parámetros gruesos, para comparar en igualdad."""
    sl = np.array(config.OTRAS_SL)
    tp = np.array(config.OTRAS_TP)
    valor, indice = fijo(op, velas, sl, tp)
    nombres = [f"SL {s} · TP {t}" for s in sl for t in tp]
    return valor.ravel().astype(float).tolist(), indice.ravel().tolist(), nombres


OTRAS_SALIDAS = {
    "SL/TP fijos (misma cuadrícula gruesa)": fijo_grueso,
    "Salida parcial (2 contratos)": parcial,
    "Trailing por ticks": trailing,
    "Stop al cierre de vela": cierre_de_vela,
    "Salir si no reacciona": sin_reaccion,
}
