"""Velas de 1 minuto de todo lo que traen los archivos de ticks, para calcular indicadores como NinjaTrader.

Se construyen una vez y se guardan. Cada archivo forma parte de una "serie" continua; si un archivo
comparte una fecha con el anterior, es otro contrato (cambio de vencimiento) y empieza otra serie.
"""

import json
from pathlib import Path

import polars as pl

from validacion.extraccion import _RE_LINEA

NOMBRE_VELAS = "velas_1min.parquet"
NOMBRE_REGISTRO = "_registro_velas.json"


def _velas_archivo(ruta: Path) -> tuple[pl.DataFrame, list[str]]:
    lineas = (
        pl.scan_csv(ruta, has_header=False, separator="\x01", quote_char=None, schema={"linea": pl.String}, encoding="utf8-lossy", glob=False)
        .filter(pl.col("linea").str.contains(_RE_LINEA))
    )
    partes = pl.col("linea").str.split_exact(";", 4).struct.rename_fields(["ts", "last_p", "bid_p", "ask_p", "vol_p"])
    ticks = lineas.select(partes.alias("p")).unnest("p").select(
        (
            pl.col("ts").str.slice(0, 8).str.to_date("%Y%m%d").cast(pl.Int64) * 1440
            + pl.col("ts").str.slice(9, 2).cast(pl.Int64) * 60
            + pl.col("ts").str.slice(11, 2).cast(pl.Int64)
        ).alias("minuto"),
        pl.col("ts").str.slice(0, 8).alias("fecha"),
        (pl.col("last_p").cast(pl.Float64) * 4).round().cast(pl.Int32).alias("precio"),
        pl.col("vol_p").cast(pl.Float64).round().cast(pl.Int64).alias("vol"),
    )
    velas = ticks.group_by("minuto", maintain_order=True).agg(
        pl.col("precio").first().alias("open"), pl.col("precio").max().alias("high"),
        pl.col("precio").min().alias("low"), pl.col("precio").last().alias("close"), pl.col("vol").sum().alias("vol"),
    )
    fechas = ticks.select(pl.col("fecha").unique())
    velas, fechas = pl.collect_all([velas, fechas])
    return velas.sort("minuto"), sorted(fechas["fecha"].to_list())


def _firma(ruta: Path) -> list[int]:
    estado = ruta.stat()
    return [estado.st_size, estado.st_mtime_ns]


def cargar_velas(carpeta_data: Path, carpeta_salida: Path, avisar=print) -> pl.DataFrame:
    """Columnas: archivo, serie, minuto (inicio, minutos desde 1970 UTC), open, high, low, close (ticks), vol."""
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    ruta_velas = carpeta_salida / NOMBRE_VELAS
    ruta_registro = carpeta_salida / NOMBRE_REGISTRO
    archivos = {r.name: r for r in sorted(carpeta_data.glob("*.txt"))}
    firmas = {n: _firma(r) for n, r in archivos.items()}
    if ruta_velas.exists() and ruta_registro.exists():
        registro = json.loads(ruta_registro.read_text(encoding="utf-8"))
        if registro.get("firmas") == firmas:
            return pl.read_parquet(ruta_velas)

    partes, fechas = [], {}
    for i, (nombre, ruta) in enumerate(archivos.items(), 1):
        avisar(f"  Velas de sesión {i}/{len(archivos)}: {nombre}")
        velas, fechas[nombre] = _velas_archivo(ruta)
        partes.append(velas.with_columns(pl.lit(nombre).alias("archivo")))

    orden = sorted(archivos, key=lambda n: (fechas[n][0] if fechas[n] else "", n))
    serie, previo, series = 0, None, {}
    for nombre in orden:
        if previo is not None and set(fechas[nombre]) & set(fechas[previo]):
            serie += 1
        series[nombre] = serie
        previo = nombre
    todas = pl.concat(partes).with_columns(pl.col("archivo").replace_strict(series, return_dtype=pl.Int64).alias("serie"))
    todas = todas.sort(["serie", "minuto"])
    temporal = ruta_velas.with_suffix(".tmp")
    todas.write_parquet(temporal, compression="zstd")
    temporal.replace(ruta_velas)
    ruta_registro.write_text(json.dumps({"firmas": firmas, "series": series}, ensure_ascii=False, indent=1), encoding="utf-8")
    return todas


def agrupar(velas: pl.DataFrame, te: int) -> pl.DataFrame:
    """Velas de `te` minutos alineadas a minutos pares UTC (inicio de sesión a las 18:00 de NY)."""
    if te == 1:
        return velas
    return (
        velas.with_columns((pl.col("minuto") // te * te).alias("bloque"))
        .group_by(["serie", "bloque"], maintain_order=True)
        .agg(pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), pl.col("close").last(), pl.col("vol").sum())
        .rename({"bloque": "minuto"})
        .sort(["serie", "minuto"])
    )
