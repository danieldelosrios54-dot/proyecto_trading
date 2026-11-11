"""Camino tick a tick de cada operación, desde la entrada hasta el cierre de la última vela posible.

Precios en ticks enteros a favor de la operación y tiempos en nanosegundos, en orden de archivo.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

import config
from medicion.entrada import Dia

_NS_MINUTO = 60_000_000_000


class Minutos(float):
    """Cierre por tiempo medido en minutos desde la entrada (en lugar de velas)."""


@dataclass(frozen=True)
class Operacion:
    fila: int  # posición de la señal en la lista de señales
    clave_dia: str
    semana: date  # lunes de la semana
    zona: str
    tipo: str
    te: int
    entrada_ns: int
    hora_utc_ns: int
    ns: np.ndarray  # ticks desde la entrada; el último es el primero en o tras el cierre de la última vela
    favor: np.ndarray  # signo × (Last − precio de entrada), en ticks
    cierres: np.ndarray  # cierres[j - 1]: índice del primer tick en o tras el cierre de la vela j
    maximo: np.ndarray = field(init=False, repr=False)  # mejor favor acumulado
    contra: np.ndarray = field(init=False, repr=False)  # peor contra acumulado, en positivo

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximo", np.maximum.accumulate(self.favor))
        object.__setattr__(self, "contra", -np.minimum.accumulate(self.favor))

    def cierre(self, velas: "int | Minutos") -> int:
        """Índice del tick que cierra por tiempo: tras `velas` velas, o tras X minutos si es `Minutos`."""
        if isinstance(velas, Minutos):
            return self.cierre_minutos(float(velas))
        return int(self.cierres[velas - 1])

    def velas_hasta_cierre(self, regla: "int | Minutos") -> int:
        """Velas que se cierran hasta el cierre por tiempo (incluida la del cierre)."""
        if not isinstance(regla, Minutos):
            return int(regla)
        c = self.cierre(regla)
        return int((self.cierres < c).sum()) + 1

    def cierre_minutos(self, minutos: float) -> int:
        """Índice del primer tick en o después de la entrada + `minutos`."""
        return min(int(np.searchsorted(self.ns, self.entrada_ns + int(minutos * _NS_MINUTO), side="left")), len(self.ns) - 1)


def lunes(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def cierre_vela_entrada(hora_utc_ns: int, entrada_ns: int, te: int) -> int:
    """Cierre de la vela donde ocurrió la entrada (las velas cierran cada Te desde Hora UTC)."""
    paso = te * _NS_MINUTO
    return hora_utc_ns + ((entrada_ns - hora_utc_ns) // paso + 1) * paso


def crear_operacion(
    fila: int, clave_dia: str, fecha: date, zona: str, tipo: str, te: int,
    dia: Dia, indice: int, precio_entrada: int, signo: int, hora_utc_ns: int,
    velas: int = config.SIM_VELAS_CAMINO,
) -> Operacion:
    entrada_ns = int(dia.ns[indice])
    primera = cierre_vela_entrada(hora_utc_ns, entrada_ns, te)
    cierres_ns = primera + np.arange(velas, dtype=np.int64) * te * _NS_MINUTO
    fin = min(int(np.searchsorted(dia.ns, cierres_ns[-1], side="left")) + 1, len(dia.ns))
    ns = dia.ns[indice:fin]
    favor = signo * (dia.last[indice:fin].astype(np.int64) - precio_entrada)
    cierres = np.minimum(np.searchsorted(ns, cierres_ns, side="left"), len(ns) - 1)
    return Operacion(fila, clave_dia, lunes(fecha), zona, tipo, te, entrada_ns, hora_utc_ns, ns, favor, cierres)
