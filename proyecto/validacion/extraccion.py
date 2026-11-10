"""Extracción de las ventanas de ticks a un Parquet por fecha y regla T1.

El Parquet conserva el orden del archivo original: no se ordena por tiempo ni se
elimina ningún tick. Un registro de origen indica de qué archivo salió cada fecha
para volver a extraer solo lo nuevo o lo que cambió.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import polars as pl

import config

NOMBRE_REGISTRO = "_registro_origen.json"

_NUM = r"\d+(\.\d+)?"
_RE_LINEA = (
    r"^\d{8} ([01]\d|2[0-3])[0-5]\d[0-5]\d \d{7}"
    rf";{_NUM};{_NUM};{_NUM};-?{_NUM}$"
)


@dataclass(frozen=True)
class Ventana:
    inicio_hms: str
    fin_hms: str

    def como_lista(self) -> list[str]:
        return [self.inicio_hms, self.fin_hms]


def hms(segundos: int) -> str:
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}{m:02d}{s:02d}"


def ruta_parquet(carpeta: Path, fecha_clave: str) -> Path:
    return carpeta / f"{fecha_clave[:4]}_{fecha_clave[4:6]}_{fecha_clave[6:]}.parquet"


def _fecha_real(texto: str) -> bool:
    try:
        datetime.strptime(texto, "%Y%m%d")
    except ValueError:
        return False
    return True


def _clasificar_lineas_malas(malas: pl.DataFrame, ventanas: dict[str, Ventana]) -> dict:
    """Aplica T1: dónde afecta cada línea que no cumple el formato."""
    resultado = {"en_ventana": {}, "sin_hora": {}, "sin_fecha": 0, "muestra": []}
    for pos, linea in malas.iter_rows():
        if len(resultado["muestra"]) < 5:
            resultado["muestra"].append({"linea": pos, "texto": linea[:120]})
        fecha = linea[:8]
        if not (fecha.isdigit() and _fecha_real(fecha)):
            resultado["sin_fecha"] += 1
            continue
        hora = linea[9:15]
        if len(linea) < 15 or linea[8] != " " or not hora.isdigit() or int(hora[:2]) > 23 or int(hora[2:4]) > 59 or int(hora[4:]) > 59:
            resultado["sin_hora"][fecha] = resultado["sin_hora"].get(fecha, 0) + 1
            continue
        ventana = ventanas.get(fecha)
        if ventana and ventana.inicio_hms <= hora < ventana.fin_hms:
            resultado["en_ventana"][fecha] = resultado["en_ventana"].get(fecha, 0) + 1
    return resultado


def _a_ticks(columna: str) -> pl.Expr:
    return (pl.col(columna) * config.TICKS_POR_PUNTO).round().cast(pl.Int32)


def _no_multiplo(columna: str) -> pl.Expr:
    valor = pl.col(columna) * config.TICKS_POR_PUNTO
    return (valor - valor.round()).abs() > 1e-9


def _parsear_ventana(crudo: pl.DataFrame) -> pl.DataFrame:
    """Convierte las líneas a columnas enteras, sin pasar por datetime."""
    partes = crudo["linea"].str.split_exact(";", 4).struct.rename_fields(["ts", "last_p", "bid_p", "ask_p", "vol_p"]).alias("p")
    numeros = crudo.with_columns(partes).unnest("p").with_columns(
        pl.col("ts").str.slice(0, 8).str.to_date("%Y%m%d").cast(pl.Int64).alias("dias"),
        pl.col("ts").str.slice(9, 2).cast(pl.Int64).alias("h"),
        pl.col("ts").str.slice(11, 2).cast(pl.Int64).alias("m"),
        pl.col("ts").str.slice(13, 2).cast(pl.Int64).alias("s"),
        pl.col("ts").str.slice(16, 7).cast(pl.Int64).alias("fraccion"),
        pl.col("last_p").cast(pl.Float64),
        pl.col("bid_p").cast(pl.Float64),
        pl.col("ask_p").cast(pl.Float64),
        pl.col("vol_p").cast(pl.Float64),
    )
    return numeros.select(
        "fecha",
        pl.col("pos").cast(pl.Int64),
        ((pl.col("dias") * 86_400 + pl.col("h") * 3600 + pl.col("m") * 60 + pl.col("s")) * 1_000_000_000 + pl.col("fraccion") * 100).alias("ns"),
        _a_ticks("last_p").alias("last"),
        _a_ticks("bid_p").alias("bid"),
        _a_ticks("ask_p").alias("ask"),
        pl.col("vol_p").round().cast(pl.Int32).alias("vol"),
        (_no_multiplo("last_p") | _no_multiplo("bid_p") | _no_multiplo("ask_p")).alias("precio_no_multiplo"),
        ((pl.col("vol_p") % 1 != 0) | (pl.col("vol_p") < 1)).alias("volumen_invalido"),
    )


def _extraer_archivo(ruta: Path, ventanas: dict[str, Ventana], carpeta: Path) -> dict:
    tabla_ventanas = pl.LazyFrame(
        {"fecha": list(ventanas), "ini": [v.inicio_hms for v in ventanas.values()], "fin": [v.fin_hms for v in ventanas.values()]},
        schema={"fecha": pl.String, "ini": pl.String, "fin": pl.String},
    )
    lineas = (
        pl.scan_csv(ruta, has_header=False, separator="\x01", quote_char=None, schema={"linea": pl.String}, encoding="utf8-lossy", glob=False)
        .with_row_index("pos", offset=1)
        .with_columns(
            pl.col("linea").str.slice(0, 8).alias("fecha"),
            pl.col("linea").str.slice(9, 6).alias("hms"),
            pl.col("linea").str.contains(_RE_LINEA).alias("ok"),
        )
    )
    en_ventana = (
        lineas.filter(pl.col("ok"))
        .join(tabla_ventanas, on="fecha", how="inner", maintain_order="left")
        .filter((pl.col("hms") >= pl.col("ini")) & (pl.col("hms") < pl.col("fin")))
        .select("pos", "fecha", "linea")
    )
    malas = lineas.filter(~pl.col("ok")).select("pos", "linea")
    fechas = lineas.filter(pl.col("ok")).select("fecha").unique()
    crudo, lineas_malas, fechas_archivo = pl.collect_all([en_ventana, malas, fechas])

    extraidas = {}
    if crudo.height:
        ticks = _parsear_ventana(crudo)
        for (fecha,), dia in ticks.group_by(["fecha"], maintain_order=True):
            destino = ruta_parquet(carpeta, fecha)
            temporal = destino.with_suffix(".tmp")
            dia.sort("pos").drop("fecha").write_parquet(temporal, compression="zstd")
            temporal.replace(destino)
            extraidas[fecha] = dia.height

    estado = ruta.stat()
    presentes = sorted(fechas_archivo["fecha"].to_list())
    return {
        "tamano": estado.st_size,
        "modificado_ns": estado.st_mtime_ns,
        "fechas_archivo": presentes,
        "ventanas": {f: ventanas[f].como_lista() for f in presentes if f in ventanas},
        "fechas_extraidas": extraidas,
        "t1": _clasificar_lineas_malas(lineas_malas, ventanas),
    }


def _necesita_extraccion(ruta: Path, entrada: dict | None, ventanas: dict[str, Ventana], carpeta: Path) -> bool:
    if entrada is None:
        return True
    estado = ruta.stat()
    if estado.st_size != entrada["tamano"] or estado.st_mtime_ns != entrada["modificado_ns"]:
        return True
    for fecha in entrada["fechas_archivo"]:
        if fecha in ventanas and entrada["ventanas"].get(fecha) != ventanas[fecha].como_lista():
            return True
    return any(not ruta_parquet(carpeta, f).exists() for f in entrada["fechas_extraidas"] if f in ventanas)


def extraer(carpeta_data: Path, carpeta_salida: Path, ventanas: dict[str, Ventana], avisar=print) -> tuple[dict, list[str]]:
    """Extrae lo que falte y devuelve (registro de origen, archivos procesados)."""
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    ruta_registro = carpeta_salida / NOMBRE_REGISTRO
    registro = json.loads(ruta_registro.read_text(encoding="utf-8")) if ruta_registro.exists() else {"archivos": {}}
    archivos = registro["archivos"]
    actuales = {r.name: r for r in sorted(carpeta_data.glob("*.txt"))}

    pendientes = {n for n, r in actuales.items() if _necesita_extraccion(r, archivos.get(n), ventanas, carpeta_salida)}
    retirados = set(archivos) - set(actuales)

    # Si una fecha estaba repartida con un archivo que cambia, los demás que la tenían también se repasan.
    tocadas = {f for n in pendientes | retirados if n in archivos for f in archivos[n]["fechas_extraidas"]}
    pendientes |= {n for n in set(actuales) & set(archivos) if tocadas & set(archivos[n]["fechas_extraidas"])}
    tocadas |= {f for n in pendientes if n in archivos for f in archivos[n]["fechas_extraidas"]}

    for fecha in tocadas:
        ruta_parquet(carpeta_salida, fecha).unlink(missing_ok=True)
    for nombre in retirados:
        del archivos[nombre]

    def guardar() -> None:
        temporal = ruta_registro.with_suffix(".tmp")
        temporal.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
        temporal.replace(ruta_registro)

    if retirados:
        guardar()
    procesados = sorted(pendientes)
    for i, nombre in enumerate(procesados, 1):
        avisar(f"  Extrayendo {i}/{len(procesados)}: {nombre}")
        archivos[nombre] = _extraer_archivo(actuales[nombre], ventanas, carpeta_salida)
        guardar()
    return registro, procesados


def fecha_de_clave(clave: str) -> date:
    return datetime.strptime(clave, "%Y%m%d").date()
