"""Reglas T2 a T12 y tramo de ticks que necesita cada señal.

T9, T10 y T11 afectan a una señal solo si caen dentro de su tramo. El resto de
reglas se aplican a toda la fecha.
"""

import statistics
from dataclasses import dataclass, field
from datetime import date

import polars as pl

import config
from validacion.modelos import Motivo, Senal, hora_texto, ns_del_dia

_NS = 1_000_000_000


@dataclass(frozen=True)
class Incidente:
    regla: str
    inicio_ns: int
    fin_ns: int
    ticks: int | None = None
    pausa_ms: int | None = None
    volumen: int | None = None

    @property
    def segundos(self) -> float:
        return (self.fin_ns - self.inicio_ns) / _NS


@dataclass
class ResultadoFecha:
    clave: str
    fecha: date
    ticks: int = 0
    volumen: int = 0
    motivos: list[Motivo] = field(default_factory=list)
    incidentes: list[Incidente] = field(default_factory=list)


def tramo_ns(s: Senal) -> tuple[int, int] | None:
    """Inicio de la Vela OP hasta Hora UTC + ventana de ejecución + posición abierta."""
    if s.fecha is None or s.te not in config.VALORES_TE or s.hora_utc_s is None or s.vela_op_utc_s is None or s.zona not in config.ZONAS:
        return None
    velas = config.VELAS_EJECUCION_CORTA if s.zona in config.ZONAS_PRIMERA_VELA | config.ZONAS_IMPULSO else config.VELAS_EJECUCION_LARGA
    inicio = ns_del_dia(s.fecha, s.vela_op_utc_s) - s.te * 60 * _NS
    fin = ns_del_dia(s.fecha, s.hora_utc_s) + (velas * s.te + config.MINUTOS_POSICION_ABIERTA) * 60 * _NS
    return inicio, fin


def validar_dia(resultado: ResultadoFecha, ticks: pl.DataFrame, inicio_ns: int, fin_ns: int) -> None:
    """Aplica las reglas sobre los ticks de una ventana, en orden de archivo."""
    resultado.ticks = ticks.height
    resultado.volumen = int(ticks["vol"].sum())

    def contar(condicion: pl.Expr) -> int:
        return ticks.select(condicion.sum()).item()

    for regla, accion, condicion, texto in (
        ("T3", config.INVALIDAR, pl.col("ns").diff() < 0, "ticks con tiempo menor que el anterior"),
        ("T5", config.INVALIDAR, pl.col("precio_no_multiplo"), "ticks con precio no múltiplo de 0.25"),
        ("T6", config.INVALIDAR, pl.col("volumen_invalido"), "ticks con volumen no entero o menor que 1"),
        ("T7", config.NOTIFICAR, pl.col("bid") > pl.col("ask"), "ticks con Bid mayor que Ask"),
        ("T8", config.NOTIFICAR, (pl.col("last") < pl.col("bid")) | (pl.col("last") > pl.col("ask")), "ticks con Last fuera del spread"),
    ):
        cantidad = contar(condicion)
        if cantidad:
            resultado.motivos.append(Motivo(regla, accion, f"{cantidad} {texto}"))

    saltos = ticks.with_columns(
        pl.col("last").diff().abs().alias("salto"),
        pl.col("ns").diff().alias("pausa"),
    ).filter(pl.col("salto") > config.T9_SALTO_TICKS)
    for ns, salto, pausa, volumen in saltos.select("ns", "salto", "pausa", "vol").iter_rows():
        resultado.incidentes.append(Incidente("T9", ns, ns, int(salto), pausa // 1_000_000, int(volumen)))

    bordes = pl.concat([pl.Series("ns", [inicio_ns], dtype=pl.Int64), ticks["ns"], pl.Series("ns", [fin_ns], dtype=pl.Int64)])
    tiempos = pl.DataFrame({"fin": bordes}).with_columns(pl.col("fin").shift(1).alias("ini"))
    minimo = config.T10_HUECO_MIN_S * _NS
    maximo = config.T11_HUECO_MAX_S * _NS
    huecos = tiempos.filter((pl.col("fin") - pl.col("ini")) >= minimo)
    for fin, ini in huecos.iter_rows():
        resultado.incidentes.append(Incidente("T11" if fin - ini > maximo else "T10", ini, fin))


def aplicar_t12(resultados: dict[str, ResultadoFecha]) -> float:
    """Marca las fechas con volumen menor al umbral respecto a la mediana. Devuelve la mediana."""
    volumenes = [r.volumen for r in resultados.values() if r.ticks]
    if not volumenes:
        return 0.0
    mediana = statistics.median(volumenes)
    for r in resultados.values():
        if r.ticks and r.volumen < config.T12_FRACCION_MEDIANA * mediana:
            r.motivos.append(Motivo("T12", config.NOTIFICAR, f"volumen de la ventana es {100 * r.volumen / mediana:.0f} % de la mediana"))
    return mediana


def en_tramo(incidente: Incidente, tramo: tuple[int, int] | None) -> bool:
    if tramo is None:
        return True
    inicio, fin = tramo
    if incidente.regla == "T9":
        return inicio <= incidente.inicio_ns < fin
    return incidente.inicio_ns < fin and incidente.fin_ns > inicio


def motivos_senal(s: Senal, resultado: ResultadoFecha | None) -> list[Motivo]:
    """Motivos de ticks de una señal, según su fecha y su tramo."""
    if resultado is None:
        return [Motivo("T2", config.INVALIDAR, "la señal no tiene una fecha con ventana de ticks")]
    motivos = list(resultado.motivos)
    tramo = tramo_ns(s)
    tocan = [i for i in resultado.incidentes if en_tramo(i, tramo)]

    saltos = [i for i in tocan if i.regla == "T9"]
    if saltos:
        mayor = max(saltos, key=lambda i: i.ticks)
        motivos.append(Motivo("T9", config.NOTIFICAR, f"{len(saltos)} salto(s) de más de {config.T9_SALTO_TICKS} ticks en su tramo; el mayor, {mayor.ticks} ticks a las {hora_texto(mayor.inicio_ns)}"))
    for i in tocan:
        if i.regla in ("T10", "T11"):
            accion = config.INVALIDAR if i.regla == "T11" else config.NOTIFICAR
            motivos.append(Motivo(i.regla, accion, f"hueco de {i.segundos:.3f} s en su tramo, de {hora_texto(i.inicio_ns)} a {hora_texto(i.fin_ns)}"))
    return motivos


def estado_fecha(resultado: ResultadoFecha) -> str:
    if any(m.accion == config.INVALIDAR for m in resultado.motivos):
        return config.INVALIDA
    return config.NOTIFICADA if resultado.motivos or resultado.incidentes else config.VALIDA
