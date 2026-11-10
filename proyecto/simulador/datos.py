"""Operaciones de cada escenario con sus etiquetas (semana, día, zona...) y matrices por combinación."""

from dataclasses import dataclass
from datetime import date

import numpy as np

import config
from medicion.analisis import Medicion
from medicion.entrada import Dia, signo_de
from simulador import salidas
from simulador.operaciones import Operacion, crear_operacion, lunes
from validacion.modelos import clave_fecha, ns_del_dia

_NS_MINUTO = 60_000_000_000
LADO = len(config.SIM_TICKS)


@dataclass
class Conjunto:
    """Operaciones ejecutadas de un escenario, ordenadas por hora de entrada, y sus etiquetas."""
    ops: list[Operacion]
    entrada_ns: np.ndarray
    hora_utc_ns: np.ndarray
    semana: np.ndarray  # índice en `semanas`
    dia: np.ndarray  # índice en `dias`
    zona: np.ndarray  # índice en `zonas`
    te: np.ndarray
    compra: np.ndarray
    minutos: np.ndarray  # desde la apertura hasta la entrada

    def __len__(self) -> int:
        return len(self.ops)


@dataclass
class Calendario:
    semanas: list[date]
    dias: list[str]
    zonas: list[str]


def calendario(mediciones: list[Medicion], dias: dict[str, Dia]) -> Calendario:
    ej = [m for m in mediciones if m.ejecucion == config.EJECUTADA]
    return Calendario(
        sorted({lunes(m.senal.fecha) for m in ej}),
        sorted(dias),
        sorted({str(m.senal.zona) for m in mediciones if m.revision == config.REVISION_VALIDA}),
    )


def conjunto(ops: list[Operacion], dias: dict[str, Dia], cal: Calendario) -> Conjunto:
    ops = sorted(ops, key=lambda o: (o.entrada_ns, o.fila))
    return Conjunto(
        ops,
        np.array([o.entrada_ns for o in ops], dtype=np.int64),
        np.array([o.hora_utc_ns for o in ops], dtype=np.int64),
        np.array([cal.semanas.index(o.semana) for o in ops], dtype=np.int64),
        np.array([cal.dias.index(o.clave_dia) for o in ops], dtype=np.int64),
        np.array([cal.zonas.index(o.zona) for o in ops], dtype=np.int64),
        np.array([o.te for o in ops], dtype=np.int64),
        np.array([o.tipo == "Buy" for o in ops]),
        np.array([(o.entrada_ns - dias[o.clave_dia].apertura_ns) / _NS_MINUTO for o in ops]),
    )


def operaciones_de(mediciones: list[Medicion], dias: dict[str, Dia]) -> list[Operacion]:
    ops = []
    for m in mediciones:
        if m.ejecucion != config.EJECUTADA:
            continue
        s = m.senal
        ops.append(crear_operacion(
            s.fila, clave_fecha(s.fecha), s.fecha, str(s.zona), str(s.tipo), s.te, dias[clave_fecha(s.fecha)],
            m.indice, m.precio_entrada, signo_de(s), ns_del_dia(s.fecha, s.hora_utc_s),
        ))
    return ops


def inversas(c: Conjunto, dias: dict[str, Dia], deslizamiento: int) -> list[Operacion]:
    """Mismo instante de entrada, dirección contraria, mismo deslizamiento."""
    ops = []
    for o in c.ops:
        dia = dias[o.clave_dia]
        i = int(np.searchsorted(dia.ns, o.entrada_ns))
        signo = -1 if o.tipo == "Buy" else 1
        ops.append(crear_operacion(
            o.fila, o.clave_dia, _fecha(o.clave_dia), o.zona, "Buy" if signo == 1 else "Sell", o.te, dia,
            i, int(dia.last[i]) + signo * deslizamiento, signo, o.hora_utc_ns,
        ))
    return ops


def al_azar(c: Conjunto, dias: dict[str, Dia], azar: np.random.Generator, demora_ms: int, deslizamiento: int) -> list[Operacion]:
    """Cada operación se repite el mismo minuto de otro día al azar, en dirección al azar, a mercado."""
    claves = sorted(dias)
    ops = []
    for o in c.ops:
        otro = claves[int(azar.integers(len(claves)))]
        while otro == o.clave_dia:
            otro = claves[int(azar.integers(len(claves)))]
        dia = dias[otro]
        hora = dia.apertura_ns + (o.hora_utc_ns - dias[o.clave_dia].apertura_ns)
        i = min(int(np.searchsorted(dia.ns, hora + demora_ms * 1_000_000)), len(dia.ns) - 1)
        signo = 1 if azar.random() < 0.5 else -1
        ops.append(crear_operacion(
            o.fila, otro, _fecha(otro), o.zona, "Buy" if signo == 1 else "Sell", o.te, dia,
            i, int(dia.last[i]) + signo * deslizamiento, signo, hora,
        ))
    return ops


def _fecha(clave: str) -> date:
    return date(int(clave[:4]), int(clave[4:6]), int(clave[6:]))


@dataclass
class Matriz:
    valores: np.ndarray  # USD por operación y combinación
    salida_ns: np.ndarray
    cerrada_be: np.ndarray | None = None


def matriz(c: Conjunto, velas: int, gestion: str = "fijo", nivel: int | None = None) -> Matriz:
    n, cols = len(c), LADO * LADO
    valores = np.empty((n, cols), dtype=np.float32)
    salida = np.empty((n, cols), dtype=np.int64)
    be = np.zeros((n, cols), dtype=bool) if gestion == "breakeven" else None
    for k, op in enumerate(c.ops):
        if gestion == "fijo":
            v, i = salidas.fijo(op, velas)
        elif gestion == "breakeven":
            v, i, cerrada = salidas.breakeven(op, velas, nivel)
            be[k] = cerrada.ravel()
        elif gestion == "sl_tiempo":
            v, i = salidas.sl_tiempo(op, velas)
        else:
            raise ValueError(gestion)
        valores[k] = salidas.usd(v).ravel()
        salida[k] = op.ns[i].ravel()
    return Matriz(valores, salida, be)


def matriz_lista(c: Conjunto, velas: int, funcion) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Para las otras salidas: (valores USD, salida_ns, nombres de parámetros)."""
    valores, salida, nombres = [], [], []
    for op in c.ops:
        v, i, nombres = funcion(op, velas)
        valores.append(salidas.usd(np.array(v)))
        salida.append(op.ns[np.array(i)])
    return np.array(valores, dtype=np.float32), np.array(salida, dtype=np.int64), nombres


def combinacion(indice: int) -> tuple[int, int]:
    """(SL, TP) en ticks de una columna de la cuadrícula."""
    sl, tp = divmod(indice, LADO)
    return config.SIM_TICKS[sl], config.SIM_TICKS[tp]
