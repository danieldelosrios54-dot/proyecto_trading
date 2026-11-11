"""Escritura de los 4 archivos del simulador (modo de solo escritura de openpyxl, más rápido)."""

import math
from datetime import date
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from medicion.analisis import Tabla

FORMATOS = {
    "SL (USD)": "0.00", "TP (USD)": "0.00", "Ganancia Neta": "#,##0.00", "Esperanza Matematica": "0.00",
    "Drawdown": "#,##0.00", "$ Peor Dia": "#,##0.00", "Profit Factor": "0.00", "Payoff Ratio": "0.00",
    "Recovery Factor": "0.00", "Win Rate": "0.0", "Hora Entrada": "h:mm:ss.000 AM/PM",
    "Ventana Ejecucion": "h:mm:ss.000", "Prom. Tiempo Abierta": "h:mm:ss.000", "Fecha Peor Dia": "yyyy-mm-dd",
    "Fecha": "yyyy-mm-dd", "Hora UTC": "h:mm",
    "Combinaciones Vecinas": "#,##0.00", "Peor mitad": "#,##0.00",
}


def limpiar(valor):
    """Convierte tipos de numpy y vacía NaN o infinitos."""
    if isinstance(valor, (np.floating, float)):
        return None if not math.isfinite(float(valor)) else float(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.bool_):
        return bool(valor)
    return valor


_VERDE = PatternFill("solid", fgColor="C6EFCE")
_ROJO = PatternFill("solid", fgColor="FFC7CE")
_AMARILLO = PatternFill("solid", fgColor="FFEB9C")


class Resaltado(str):
    """Texto que se escribe con fondo amarillo (por ejemplo, un paso que cambia frente a la referencia)."""


def _hoja(libro: Workbook, tabla: Tabla, colores: set[str] = frozenset()) -> None:
    hoja = libro.create_sheet(tabla.titulo[:31])
    ancho = len(tabla.encabezados)
    for i, nombre in enumerate(tabla.encabezados, 1):
        hoja.column_dimensions[get_column_letter(i)].width = max(10, min(len(str(nombre)) + 2, 34))
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{get_column_letter(ancho)}{len(tabla.filas) + 1}"
    negrita = Font(bold=True)
    encabezado = []
    for nombre in tabla.encabezados:
        celda = WriteOnlyCell(hoja, nombre)
        celda.font = negrita
        encabezado.append(celda)
    hoja.append(encabezado)
    formatos = [FORMATOS.get(n) for n in tabla.encabezados]
    colorear = [n in colores for n in tabla.encabezados]
    for fila in tabla.filas:
        salida = []
        for valor, formato, color in zip(fila, formatos, colorear):
            if isinstance(valor, Resaltado):
                celda = WriteOnlyCell(hoja, str(valor))
                celda.fill = _AMARILLO
                salida.append(celda)
                continue
            valor = limpiar(valor)
            pinta = color and isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor != 0
            if (formato or pinta) and valor is not None:
                celda = WriteOnlyCell(hoja, valor)
                if formato:
                    celda.number_format = formato
                if pinta:
                    celda.fill = _VERDE if valor > 0 else _ROJO
                salida.append(celda)
            else:
                salida.append(valor)
        hoja.append(salida)


def escribir_libro(ruta: Path, tablas: list[Tabla], colores: dict[str, set[str]] | None = None) -> None:
    """`colores`: por título de pestaña, columnas que se pintan de verde (positivo) o rojo (negativo)."""
    libro = Workbook(write_only=True)
    for tabla in tablas:
        _hoja(libro, tabla, (colores or {}).get(tabla.titulo, frozenset()))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp.xlsx")
    libro.save(temporal)
    temporal.replace(ruta)


COLUMNAS_19 = [
    "Revision Invalida", "No Ejecutadas", "Hora Entrada", "Ventana Ejecucion", "Ganancia Neta", "Esperanza Matematica",
    "Profit Factor", "Win Rate", "Payoff Ratio", "Drawdown", "Recovery Factor", "Trades +", "Trades -",
    "Racha Max. (Trades -)", "Racha Max. (Dias -)", "Trades (Solapamiento)", "$ Peor Dia", "Fecha Peor Dia", "Prom. Tiempo Abierta",
]
ENCABEZADOS_COMBINACIONES = ["SL (ticks)", "TP (ticks)", "SL (USD)", "TP (USD)", *COLUMNAS_19]


def tabla_combinaciones(titulo: str, columnas: dict[str, np.ndarray], ticks: tuple[int, ...], usd_por_tick: float, fechas: list[date]) -> Tabla:
    lado = len(ticks)
    filas = []
    valores = {n: columnas[n].tolist() for n in COLUMNAS_19}
    for i in range(lado * lado):
        sl, tp = ticks[i // lado], ticks[i % lado]
        fila = [sl, tp, sl * usd_por_tick, tp * usd_por_tick]
        for n in COLUMNAS_19:
            v = valores[n][i]
            if n == "Fecha Peor Dia":
                v = fechas[v] if v >= 0 else None
            fila.append(v)
        filas.append(fila)
    return Tabla(titulo, ENCABEZADOS_COMBINACIONES, filas)
