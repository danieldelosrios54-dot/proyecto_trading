"""Velas armadas con ticks reales y regla R13 (color de la vela "Hora UTC")."""

from dataclasses import dataclass

import polars as pl

import config
from validacion.modelos import Motivo, Senal, ns_del_dia

_NS = 1_000_000_000


@dataclass(frozen=True)
class Vela:
    open: int
    high: int
    low: int
    close: int
    volumen: int


def armar_vela(ticks: pl.DataFrame, cierre_ns: int, te_minutos: int) -> Vela | None:
    """Vela con cierre T: incluye T − Te ≤ tiempo < T, en orden de archivo. Precios en ticks enteros."""
    apertura_ns = cierre_ns - te_minutos * 60 * _NS
    dentro = ticks.filter((pl.col("ns") >= apertura_ns) & (pl.col("ns") < cierre_ns))
    if dentro.is_empty():
        return None
    precios = dentro["last"]
    return Vela(precios[0], precios.max(), precios.min(), precios[-1], int(dentro["vol"].sum()))


def regla_r13(s: Senal, ticks: pl.DataFrame) -> list[Motivo]:
    """Buy exige vela verde, Sell vela roja; "1er Vela (VC)" admite cualquier color."""
    if s.zona == config.ZONA_VC or s.fecha is None or s.hora_utc_s is None or s.te not in config.VALORES_TE or s.tipo not in config.VALORES_TIPO:
        return []
    vela = armar_vela(ticks, ns_del_dia(s.fecha, s.hora_utc_s), s.te)
    if vela is None:
        return []  # sin ticks en la vela: ya queda invalidada por T11 dentro de su tramo
    if vela.close == vela.open:
        return [Motivo("R13", config.NOTIFICAR, "la vela Hora UTC abre y cierra en el mismo precio")]
    esperado_verde = s.tipo == "Buy"
    if (vela.close > vela.open) != esperado_verde:
        color = "verde" if vela.close > vela.open else "roja"
        apertura, cierre = vela.open / config.TICKS_POR_PUNTO, vela.close / config.TICKS_POR_PUNTO
        return [Motivo("R13", config.INVALIDAR, f"señal {s.tipo} con vela Hora UTC {color} (abre {apertura:.2f}, cierra {cierre:.2f})")]
    return []
