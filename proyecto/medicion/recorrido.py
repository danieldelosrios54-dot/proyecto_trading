"""MFE, Hora MFE, MAE pre MFE y MAE desde la Hora y el Precio de Entrada."""

from dataclasses import dataclass

import numpy as np

import config
from medicion.entrada import Dia

_NS_MINUTO = 60_000_000_000


@dataclass(frozen=True)
class Recorrido:
    mfe: int
    hora_mfe_ns: int
    mae_pre_mfe: int
    mae: int


@dataclass(frozen=True)
class TrasFavor:
    llega: bool
    vuelve_a_entrada: bool
    maximo: int | None  # MFE de las que llegan y no vuelven


def recorridos(dia: Dia, indice: int, precio_entrada: int, signo: int, horizontes=config.HORIZONTES) -> dict[int, Recorrido]:
    """Por cada X: desde el tick de entrada, incluido, hasta entrada + X minutos, sin incluirlo."""
    t0 = int(dia.ns[indice])
    finales = np.searchsorted(dia.ns, [t0 + x * _NS_MINUTO for x in horizontes])
    favor = signo * (dia.last[indice:int(finales[-1])] - precio_entrada)
    resultado = {}
    for x, fin in zip(horizontes, finales):
        tramo = favor[: int(fin) - indice]
        primera_vez = int(np.argmax(tramo))
        resultado[x] = Recorrido(
            mfe=int(tramo[primera_vez]),
            hora_mfe_ns=int(dia.ns[indice + primera_vez]),
            mae_pre_mfe=int((-tramo[: primera_vez + 1]).max()),
            mae=int((-tramo).max()),
        )
    return resultado


def tras_ir_a_favor(dia: Dia, indice: int, precio_entrada: int, signo: int, nivel: int, minutos: int = config.HORIZONTES[-1]) -> TrasFavor:
    """Tras llegar por primera vez a +nivel ticks, ¿volvió a la entrada dentro de la ventana?"""
    fin = int(np.searchsorted(dia.ns, int(dia.ns[indice]) + minutos * _NS_MINUTO))
    favor = signo * (dia.last[indice:fin] - precio_entrada)
    llegadas = np.flatnonzero(favor >= nivel)
    if llegadas.size == 0:
        return TrasFavor(False, False, None)
    posterior = favor[int(llegadas[0]):]
    vuelve = bool((posterior <= 0).any())
    return TrasFavor(True, vuelve, None if vuelve else int(posterior.max()))
