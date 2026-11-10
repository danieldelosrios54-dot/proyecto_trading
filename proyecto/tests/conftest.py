from datetime import datetime, time

import polars as pl
import pytest

from validacion.registro import crear_senal


def _crudo_base() -> dict:
    return {
        "Fecha": datetime(2026, 9, 14), "Hora": time(8, 40), "Te": 1, "Zona Reacción": "Trend 1er Pivot",
        "M": "A", "Tipo": "Buy", "Vela OP": time(8, 40), "Condiciones Estructura": "-",
        "Condiciones Continuidad": "-", "SE": "-", "SC": "-", "D": "-",
        "Notas (Duda / C. Fuerte)": "-", "ID": 1, "Hora UTC": time(13, 40),
        "Vela OP UTC": time(13, 40), "Apertura UTC": time(13, 30), "OHLC": "High",
    }


@pytest.fixture
def senal():
    """Crea una señal válida, con los cambios indicados en sus columnas."""

    def crear(fila=3, **cambios):
        crudo = _crudo_base()
        crudo.update({k.replace("_", " "): v for k, v in cambios.items()})
        return crear_senal(fila, crudo)

    return crear


@pytest.fixture
def tabla_ticks():
    """DataFrame con el mismo formato que los Parquet extraídos."""

    def crear(filas):
        return pl.DataFrame(
            {
                "pos": list(range(1, len(filas) + 1)),
                "ns": [f["ns"] for f in filas],
                "last": [f["last"] for f in filas],
                "bid": [f.get("bid", f["last"]) for f in filas],
                "ask": [f.get("ask", f["last"]) for f in filas],
                "vol": [f.get("vol", 1) for f in filas],
                "precio_no_multiplo": [f.get("no_multiplo", False) for f in filas],
                "volumen_invalido": [f.get("vol_mal", False) for f in filas],
            },
            schema={
                "pos": pl.Int64, "ns": pl.Int64, "last": pl.Int32, "bid": pl.Int32, "ask": pl.Int32,
                "vol": pl.Int32, "precio_no_multiplo": pl.Boolean, "volumen_invalido": pl.Boolean,
            },
        )

    return crear


def linea_tick(fecha="20260914", hms="133000", fraccion="0000000", last="100", bid=None, ask=None, vol="1"):
    return f"{fecha} {hms} {fraccion};{last};{bid or last};{ask or last};{vol}"
