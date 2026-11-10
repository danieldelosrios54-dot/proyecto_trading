"""Estructuras de datos compartidas por la validación."""

from dataclasses import dataclass
from datetime import date

import config


@dataclass(frozen=True)
class Motivo:
    regla: str
    accion: str  # config.INVALIDAR o config.NOTIFICAR
    texto: str

    def __str__(self) -> str:
        return f"{self.regla}: {self.texto}"


@dataclass
class Senal:
    fila: int
    crudo: dict
    id: int | None
    fecha: date | None
    te: int | None
    zona: object
    tipo: object
    ohlc: object
    hora_s: int | None
    vela_op_s: int | None
    hora_utc_s: int | None
    vela_op_utc_s: int | None
    apertura_s: int | None


def estado(motivos: list[Motivo]) -> str:
    if any(m.accion == config.INVALIDAR for m in motivos):
        return config.INVALIDA
    return config.NOTIFICADA if motivos else config.VALIDA


def ns_del_dia(fecha: date, segundos: int) -> int:
    """Nanosegundos desde 1970 para una fecha y una hora UTC en segundos."""
    dias = (fecha - date(1970, 1, 1)).days
    return (dias * 86_400 + segundos) * 1_000_000_000


def hora_texto(ns: int) -> str:
    """Hora UTC HH:MM:SS.mmm a partir de nanosegundos enteros."""
    ms_del_dia = (ns // 1_000_000) % 86_400_000
    segundos, ms = divmod(ms_del_dia, 1000)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def clave_fecha(fecha: date) -> str:
    return fecha.strftime("%Y%m%d")
