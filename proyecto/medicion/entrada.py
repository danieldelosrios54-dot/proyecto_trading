"""Colocación, reintento y disparo de la orden pendiente de cada señal.

Este motor es común a MFE/MAE y al simulador de combinaciones. Los precios van en
ticks enteros y el tiempo en nanosegundos enteros, siempre en orden de archivo.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

import config
from validacion.modelos import Senal, ns_del_dia
from validacion.velas import armar_vela

_NS_MINUTO = 60_000_000_000
_NS_MS = 1_000_000


@dataclass(frozen=True)
class Escenario:
    numero: int
    distancia: int
    demora_ms: int
    deslizamiento: int
    limite_reentrada: int = config.LIMITE_REENTRADA_TICKS


ESCENARIOS = tuple(Escenario(*e) for e in config.ESCENARIOS)


@dataclass(frozen=True)
class Dia:
    tabla: pl.DataFrame
    ns: np.ndarray
    last: np.ndarray
    vol: np.ndarray
    apertura_ns: int


def crear_dia(tabla: pl.DataFrame, apertura_ns: int) -> Dia:
    return Dia(tabla, tabla["ns"].to_numpy(), tabla["last"].to_numpy().astype(np.int64), tabla["vol"].to_numpy().astype(np.int64), apertura_ns)


def cargar_dia(ruta: Path, apertura_ns: int) -> Dia:
    return crear_dia(pl.read_parquet(ruta, columns=["ns", "last", "vol"]), apertura_ns)


@dataclass(frozen=True)
class Entrada:
    estado: str
    indice: int | None = None


def signo_de(senal: Senal) -> int:
    return 1 if senal.tipo == "Buy" else -1


def precio_base_y_cierre(senal: Senal, dia: Dia) -> tuple[int, int] | None:
    """Precio "OHLC" de la vela Vela OP y Close de la vela Hora UTC, en ticks."""
    vela_op = armar_vela(dia.tabla, ns_del_dia(senal.fecha, senal.vela_op_utc_s), senal.te)
    vela_hora = armar_vela(dia.tabla, ns_del_dia(senal.fecha, senal.hora_utc_s), senal.te)
    if vela_op is None or vela_hora is None:
        return None
    base = {"High": vela_op.high, "Low": vela_op.low, "Close": vela_op.close}[senal.ohlc]
    return base, vela_hora.close


def precio_orden(base: int, signo: int, escenario: Escenario) -> int:
    return base + signo * escenario.distancia


def orden_valida(precio_op: int, cierre: int, signo: int) -> bool:
    return signo * (precio_op - cierre) > 0


def _velas_ejecucion(senal: Senal) -> int:
    corta = senal.zona in config.ZONAS_PRIMERA_VELA | config.ZONAS_IMPULSO
    return config.VELAS_EJECUCION_CORTA if corta else config.VELAS_EJECUCION_LARGA


def simular_entrada(senal: Senal, dia: Dia, precio_op: int, escenario: Escenario) -> Entrada:
    """Coloca la orden, reintenta si el precio ya la pasó y busca el disparo."""
    ns, last = dia.ns, dia.last
    signo = signo_de(senal)
    hora_ns = ns_del_dia(senal.fecha, senal.hora_utc_s)
    fin_ns = hora_ns + _velas_ejecucion(senal) * senal.te * _NS_MINUTO
    demora_ns = escenario.demora_ms * _NS_MS

    inicio = int(np.searchsorted(ns, hora_ns))
    fin = int(np.searchsorted(ns, fin_ns))
    siguiente = int(np.searchsorted(ns, hora_ns + demora_ns, side="right"))
    bloqueada = False

    while siguiente < fin and siguiente >= 1:
        if signo * (last[siguiente - 1] - precio_op) < 0:  # aún no llega a la orden: se coloca
            tramo = signo * (last[siguiente:fin] - precio_op)
            disparos = np.flatnonzero(tramo >= 0)
            if disparos.size:
                return Entrada(config.EJECUTADA, siguiente + int(disparos[0]))
            return Entrada(config.NO_EJECUTADA)

        bloqueada = True
        tramo = signo * (last[siguiente:fin] - precio_op)
        regresos = np.flatnonzero(tramo < 0)
        if regresos.size == 0:
            return Entrada(config.NO_EJECUTADA_OP)
        regreso = int(regresos[0])
        previo = signo * (last[inicio:siguiente + regreso] - precio_op)
        if previo.size and previo.max() > escenario.limite_reentrada:
            return Entrada(config.NO_EJECUTADA_OP)
        siguiente = int(np.searchsorted(ns, int(ns[siguiente + regreso]) + demora_ns, side="right"))

    return Entrada(config.NO_EJECUTADA_OP if bloqueada else config.NO_EJECUTADA)
