"""Solapamiento, las 19 columnas de cada combinación y la calificación dentro y fuera de muestra.

Las matrices tienen una fila por operación y una columna por combinación.
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

import config

NS_DIA = 86_400_000_000_000
_MAX = np.iinfo(np.int64).max


def tomar_sin_solape(entrada_ns: np.ndarray, salida_ns: np.ndarray) -> np.ndarray:
    """Una señal se pierde solo si al llegar el precio a su orden sigue abierta otra operación."""
    tomada = np.zeros(salida_ns.shape, dtype=bool)
    libre = np.full(salida_ns.shape[1], np.iinfo(np.int64).min, dtype=np.int64)
    for k in np.argsort(entrada_ns, kind="stable"):
        entra = entrada_ns[k] >= libre
        tomada[k] = entra
        libre = np.where(entra, salida_ns[k], libre)
    return tomada


def _division(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def _uno_caliente(indices: np.ndarray, n: int) -> np.ndarray:
    matriz = np.zeros((n, len(indices)))
    matriz[indices, np.arange(len(indices))] = 1.0
    return matriz


def columnas(
    valores: np.ndarray, salida_ns: np.ndarray, tomada: np.ndarray,
    entrada_ns: np.ndarray, hora_utc_ns: np.ndarray, dia: np.ndarray, n_dias: int,
    revision_invalida: int, no_ejecutadas: int, con_solape: bool,
) -> dict[str, np.ndarray]:
    """Las 19 columnas del documento 3 para cada combinación. `dia`: índice de día de cada operación."""
    n, c = valores.shape
    v = np.where(tomada, valores, 0.0).astype(np.float64)
    ops = tomada.sum(0)
    positivas = ((v > 0) & tomada).sum(0)
    negativas = ((v < 0) & tomada).sum(0)
    ganancia = np.maximum(v, 0).sum(0)
    perdida = np.maximum(-v, 0).sum(0)
    neto = v.sum(0)

    clave = np.where(tomada, salida_ns, _MAX)
    orden = np.argsort(clave, axis=0, kind="stable")
    v_orden = np.take_along_axis(v, orden, axis=0)
    t_orden = np.take_along_axis(tomada, orden, axis=0)
    acumulado = np.cumsum(v_orden, axis=0)
    pico = np.maximum.accumulate(np.maximum(acumulado, 0), axis=0)
    caida = (pico - acumulado).max(0) if n else np.zeros(c)
    racha = np.zeros(c, dtype=np.int64)
    mejor = np.zeros(c, dtype=np.int64)
    for fila, toma in zip(v_orden, t_orden):
        racha = np.where(toma, np.where(fila < 0, racha + 1, 0), racha)
        mejor = np.maximum(mejor, racha)

    por_dia = _uno_caliente(dia, n_dias)
    neto_dia = por_dia @ v
    ops_dia = por_dia @ tomada.astype(np.float64)
    con_ops = ops_dia > 0
    peor = np.where(con_ops, neto_dia, np.inf)
    dia_peor = peor.argmin(0)
    racha_d = np.zeros(c, dtype=np.int64)
    mejor_d = np.zeros(c, dtype=np.int64)
    for neto_d, hay in zip(neto_dia, con_ops):
        racha_d = np.where(hay, np.where(neto_d < 0, racha_d + 1, 0), racha_d)
        mejor_d = np.maximum(mejor_d, racha_d)

    pesos = tomada.astype(np.float64)
    hora = ((entrada_ns % NS_DIA).astype(np.float64) / NS_DIA) @ pesos
    ventana = ((entrada_ns - hora_utc_ns).astype(np.float64) / NS_DIA) @ pesos
    abierta = (((salida_ns - entrada_ns[:, None]) * tomada).astype(np.float64) / NS_DIA).sum(0)
    return {
        "Revision Invalida": np.full(c, revision_invalida),
        "No Ejecutadas": np.full(c, no_ejecutadas),
        "Hora Entrada": _division(hora, ops),
        "Ventana Ejecucion": _division(ventana, ops),
        "Ganancia Neta": neto,
        "Esperanza Matematica": _division(neto, ops),
        "Profit Factor": _division(ganancia, perdida),
        "Win Rate": _division(100.0 * positivas, ops),
        "Payoff Ratio": _division(_division(ganancia, positivas), _division(perdida, negativas)),
        "Drawdown": caida,
        "Recovery Factor": _division(neto, caida),
        "Trades +": positivas,
        "Trades -": negativas,
        "Racha Max. (Trades -)": mejor,
        "Racha Max. (Dias -)": mejor_d,
        "Trades (Solapamiento)": (n - ops) if con_solape else np.zeros(c, dtype=np.int64),
        "$ Peor Dia": np.where(np.isfinite(peor.min(0)), peor.min(0), np.nan),
        "Fecha Peor Dia": np.where(con_ops.any(0), dia_peor, -1),
        "Prom. Tiempo Abierta": _division(abierta, ops),
    }


@dataclass
class Semanal:
    """Sumas por semana (filas) y combinación (columnas)."""
    neto: np.ndarray
    ganancia: np.ndarray
    perdida: np.ndarray
    operaciones: np.ndarray

    def total(self) -> np.ndarray:
        return self.neto.sum(0)


def semanal(valores: np.ndarray, tomada: np.ndarray | None, semana: np.ndarray, n_semanas: int) -> Semanal:
    v = valores.astype(np.float64) if tomada is None else np.where(tomada, valores, 0.0).astype(np.float64)
    t = np.ones(valores.shape) if tomada is None else tomada.astype(np.float64)
    o = _uno_caliente(semana, n_semanas)
    return Semanal(o @ v, o @ np.maximum(v, 0), o @ np.maximum(-v, 0), o @ t)


def combinaciones_vecinas(neto: np.ndarray, lado: int) -> np.ndarray:
    """Ganancia Neta mínima de la matriz 3 × 3 (la propia y sus vecinas que existan)."""
    rejilla = np.pad(neto.reshape(lado, lado).astype(np.float64), 1, constant_values=np.nan)
    return np.nanmin(sliding_window_view(rejilla, (3, 3)), axis=(-2, -1)).ravel()


def peor_mitad(s: "Semanal") -> np.ndarray:
    """Neto de la mitad de semanas que ganó menos (primeras frente a últimas)."""
    mitad = s.neto.shape[0] // 2
    return np.minimum(s.neto[:mitad].sum(0), s.neto[mitad:].sum(0))


def semanas_positivas(s: "Semanal") -> tuple[np.ndarray, int]:
    """(Semanas con neto > 0 por combinación, semanas con operaciones)."""
    con_ops = s.operaciones.max(1) > 0
    return (s.neto[con_ops] > 0).sum(0), int(con_ops.sum())


def suavizar(neto: np.ndarray, lado: int) -> np.ndarray:
    """Promedio de cada combinación con sus vecinas en la cuadrícula SL × TP."""
    p = config.MESETA_PASOS
    rejilla = np.pad(neto.reshape(lado, lado), p, mode="edge")
    return sliding_window_view(rejilla, (2 * p + 1, 2 * p + 1)).mean((-2, -1)).ravel()


def elegir(neto: np.ndarray, lado: int | None) -> int:
    """La combinación con mejor meseta (en la cuadrícula) o la mejor (en listas de parámetros)."""
    return int(np.argmax(suavizar(neto, lado) if lado else neto))


@dataclass(frozen=True)
class Calificacion:
    neto: float
    operaciones: int
    pf: float
    semanas_positivas: int
    mitad1: float
    mitad2: float
    elegidas: tuple[int, ...]

    @property
    def esperanza(self) -> float:
        return self.neto / self.operaciones if self.operaciones else float("nan")


def _calificar(s: Semanal, elegidas: list[int]) -> Calificacion:
    semanas = np.arange(len(elegidas))
    neto = s.neto[semanas, elegidas]
    ganancia = s.ganancia[semanas, elegidas].sum()
    perdida = s.perdida[semanas, elegidas].sum()
    mitad = len(elegidas) // 2
    return Calificacion(
        float(neto.sum()), int(s.operaciones[semanas, elegidas].sum()),
        float(ganancia / perdida) if perdida else float("nan"), int((neto > 0).sum()),
        float(neto[:mitad].sum()), float(neto[mitad:].sum()), tuple(elegidas),
    )


def calificar_operaciones(valores: np.ndarray, semana: np.ndarray, n_semanas: int) -> Calificacion:
    """Calificación de una lista de operaciones ya tomadas (valores en USD)."""
    neto = np.bincount(semana, valores, n_semanas)
    ganancia = valores[valores > 0].sum()
    perdida = -valores[valores < 0].sum()
    mitad = n_semanas // 2
    return Calificacion(
        float(valores.sum()), int(len(valores)), float(ganancia / perdida) if perdida else float("nan"),
        int((neto > 0).sum()), float(neto[:mitad].sum()), float(neto[mitad:].sum()), (),
    )


def dentro_de_muestra(s: Semanal, lado: int | None) -> Calificacion:
    """Elige mirando todas las semanas y mide en las mismas."""
    elegida = elegir(s.total(), lado)
    return _calificar(s, [elegida] * s.neto.shape[0])


def fuera_de_muestra(s: Semanal, lado: int | None) -> Calificacion:
    """Cada semana se mide con lo elegido mirando solo las otras semanas."""
    total = s.total()
    return _calificar(s, [elegir(total - s.neto[w], lado) for w in range(s.neto.shape[0])])


def positivas(s: Semanal) -> tuple[int, int]:
    """(Combinaciones con neto > 0, combinaciones positivas en ambas mitades)."""
    mitad = s.neto.shape[0] // 2
    primera, segunda = s.neto[:mitad].sum(0), s.neto[mitad:].sum(0)
    return int((s.total() > 0).sum()), int(((primera > 0) & (segunda > 0)).sum())


def pbo(s: Semanal, bloque: int = 400) -> float:
    """Probabilidad de sobreajuste (CSCV): veces que la mejor de media muestra queda bajo la mediana en la otra."""
    n_sem = s.neto.shape[0]
    total = s.total()
    divisiones = np.array([[1.0 if w in c else 0.0 for w in range(n_sem)] for c in combinations(range(n_sem), n_sem // 2)])
    bajo = 0
    for i in range(0, len(divisiones), bloque):
        dentro = divisiones[i:i + bloque] @ s.neto
        fuera = total[None, :] - dentro
        mejor = fuera[np.arange(len(dentro)), dentro.argmax(1)]
        bajo += int(((fuera < mejor[:, None]).mean(1) < 0.5).sum())
    return bajo / len(divisiones)
