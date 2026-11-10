"""Indicadores de NinjaTrader 8 al cierre de la vela de confirmación, con horario ETH.

Fórmulas como el código de NinjaTrader: ATR con suavizado de Wilder (k = 1/período), ADX de Wilder,
Choppiness Index = 100·log10(ΣTR / (máximo − mínimo)) / log10(período), VOLMA = media simple del volumen.
Los primeros valores usan las velas disponibles, igual que NinjaTrader.
"""

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import polars as pl
from numpy.lib.stride_tricks import sliding_window_view

import config
from simulador.velas_sesion import agrupar

_NS_MINUTO = 60_000_000_000
_PUNTO = config.TICKS_POR_PUNTO


def rango_verdadero(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    previo = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - previo), np.abs(l - previo))).astype(np.float64)
    tr[0] = h[0] - l[0]
    return tr


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, periodo: int) -> np.ndarray:
    tr = rango_verdadero(h, l, c)
    salida = np.empty(len(tr))
    salida[0] = tr[0]
    for i in range(1, len(tr)):
        n = min(i + 1, periodo)
        salida[i] = ((n - 1) * salida[i - 1] + tr[i]) / n
    return salida


def _ventana(x: np.ndarray, periodo: int, funcion) -> np.ndarray:
    """funcion sobre las últimas `periodo` velas (o las disponibles al inicio)."""
    relleno = np.r_[np.full(periodo - 1, np.nan), x.astype(np.float64)]
    return funcion(sliding_window_view(relleno, periodo), axis=1)


def choppiness(h: np.ndarray, l: np.ndarray, c: np.ndarray, periodo: int) -> np.ndarray:
    suma_tr = _ventana(rango_verdadero(h, l, c), periodo, np.nansum)
    amplitud = _ventana(h, periodo, np.nanmax) - _ventana(l, periodo, np.nanmin)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(amplitud > 0, 100 * np.log10(suma_tr / np.where(amplitud > 0, amplitud, 1)) / np.log10(periodo), np.nan)


def adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, periodo: int) -> np.ndarray:
    n = len(h)
    salida = np.empty(n)
    salida[0] = 50.0
    suma_tr, suma_mas, suma_menos = float(h[0] - l[0]), 0.0, 0.0
    for i in range(1, n):
        tr = max(abs(l[i] - c[i - 1]), h[i] - l[i], abs(h[i] - c[i - 1]))
        sube, baja = h[i] - h[i - 1], l[i - 1] - l[i]
        mas = max(sube, 0) if sube > baja else 0
        menos = max(baja, 0) if baja > sube else 0
        if i < periodo:
            suma_tr, suma_mas, suma_menos = suma_tr + tr, suma_mas + mas, suma_menos + menos
        else:
            suma_tr = suma_tr - suma_tr / periodo + tr
            suma_mas = suma_mas - suma_mas / periodo + mas
            suma_menos = suma_menos - suma_menos / periodo + menos
        di_mas = 0.0 if suma_tr == 0 else 100 * suma_mas / suma_tr
        di_menos = 0.0 if suma_tr == 0 else 100 * suma_menos / suma_tr
        suma = di_mas + di_menos
        salida[i] = 50.0 if suma == 0 else ((periodo - 1) * salida[i - 1] + 100 * abs(di_mas - di_menos) / suma) / periodo
    return salida


def media_simple(x: np.ndarray, periodo: int) -> np.ndarray:
    return _ventana(x, periodo, np.nanmean)


def _hora_ny(minuto_inicio: np.ndarray) -> pl.Series:
    utc = pl.from_epoch(pl.Series(np.asarray(minuto_inicio, dtype=np.int64) * 60), time_unit="s").dt.replace_time_zone("UTC")
    return utc.dt.convert_time_zone(config.ZONA_HORARIA_NY)


def sesion_ny(minuto_inicio: np.ndarray) -> np.ndarray:
    """Fecha de la sesión ETH (empieza a las 18:00 de Nueva York del día anterior)."""
    return (_hora_ny(minuto_inicio) + timedelta(hours=24 - config.SESION_INICIO_HORA_NY)).dt.date().to_numpy()


@dataclass
class SerieIndicadores:
    cierre_ns: np.ndarray  # cierre de cada vela
    valores: dict[str, np.ndarray]


def _rango_del_dia(h: np.ndarray, l: np.ndarray, sesion: np.ndarray, completa: dict) -> tuple[np.ndarray, np.ndarray]:
    """(Current Day OHL H−L hasta la vela, Prior Day OHLC H−L), vacíos si la sesión está incompleta."""
    actual = np.full(len(h), np.nan)
    previo = np.full(len(h), np.nan)
    cortes = np.flatnonzero(np.r_[True, sesion[1:] != sesion[:-1], True])
    anterior = None
    for a, b in zip(cortes[:-1], cortes[1:]):
        s = sesion[a]
        if completa.get(s):
            actual[a:b] = np.maximum.accumulate(h[a:b]) - np.minimum.accumulate(l[a:b])
        if anterior is not None and completa.get(anterior[0]):
            previo[a:b] = anterior[1]
        anterior = (s, float(h[a:b].max() - l[a:b].min()))
    return actual, previo


def indicadores_serie(velas: pl.DataFrame, te: int) -> dict[int, SerieIndicadores]:
    """Por serie: arrays de cada indicador alineados con el cierre de cada vela de `te` minutos."""
    salida = {}
    base = velas.select("serie", "minuto")
    for (serie,), grupo in agrupar(velas, te).group_by(["serie"], maintain_order=True):
        minuto = grupo["minuto"].to_numpy()
        h, l, c, v = (grupo[k].to_numpy().astype(np.float64) for k in ("high", "low", "close", "vol"))
        sesion = sesion_ny(minuto)
        uno = base.filter(pl.col("serie") == serie)["minuto"].to_numpy()
        ses_uno = sesion_ny(uno)
        primeros = {}
        for s, m in zip(ses_uno, uno):
            primeros.setdefault(s, m)
        completa = {s: _completa(m) for s, m in primeros.items()}
        actual, previo = _rango_del_dia(h, l, sesion, completa)
        valores = {
            "ATR (5)": atr(h, l, c, 5) / _PUNTO,
            "ATR (10)": atr(h, l, c, 10) / _PUNTO,
            "Range": (h - l) / _PUNTO,
            "Current Day OHL (H-L)": actual / _PUNTO,
            "Prior Day OHLC (H-L)": previo / _PUNTO,
            f"Choppiness Index ({config.CHOP_PERIODO})": choppiness(h, l, c, config.CHOP_PERIODO),
            f"ADX ({config.ADX_PERIODO})": adx(h, l, c, config.ADX_PERIODO),
            f"Volumen / VOLMA ({config.VOLMA_PERIODO})": v / media_simple(v, config.VOLMA_PERIODO),
        }
        salida[serie] = SerieIndicadores((minuto + te) * _NS_MINUTO, valores)
    return salida


def _completa(primer_minuto: int) -> bool:
    """La sesión tiene velas desde su inicio (18:00 de Nueva York del día anterior)."""
    ny = _hora_ny(np.array([primer_minuto]))[0]
    minutos_desde_inicio = (ny.hour - config.SESION_INICIO_HORA_NY) * 60 + ny.minute
    return 0 <= minutos_desde_inicio < config.SESION_MARGEN_MIN


def valor_en(serie: SerieIndicadores, cierre_ns: int) -> dict[str, float]:
    """Indicadores de la vela que cierra en `cierre_ns` (vacíos si esa vela no existe)."""
    i = int(np.searchsorted(serie.cierre_ns, cierre_ns))
    if i >= len(serie.cierre_ns) or serie.cierre_ns[i] != cierre_ns:
        return {k: float("nan") for k in serie.valores}
    return {k: float(v[i]) for k, v in serie.valores.items()}
