"""Escribe resultados_mfe_mae.xlsx y analisis_mfe_mae.xlsx."""

import warnings
from pathlib import Path

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

import config
from medicion.analisis import Contexto, Medicion, Tabla
from validacion.registro import COLUMNAS

_NS_DIA = 86_400_000_000_000
_FORMATO_HORA = "h:mm:ss.000 AM/PM"
_FORMATO_DURACION = "h:mm:ss.000"
_FORMATO_PRECIO = "0.00"


def _formatos_registro() -> dict[str, str]:
    """Formato numérico de cada columna en el registro original."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hoja = openpyxl.load_workbook(config.ARCHIVO_REGISTRO, data_only=True)[config.HOJA_REGISTRO]
    fila = config.FILA_ENCABEZADOS
    return {
        str(hoja.cell(fila, c).value).strip(): hoja.cell(fila + 1, c).number_format
        for c in range(1, hoja.max_column + 1) if hoja.cell(fila, c).value is not None
    }


def _encabezados_resultados() -> list[str]:
    columnas = list(COLUMNAS) + ["Revision", "Precio OP", "Ejecucion", "Hora Entrada", "Precio Entrada", "Tiempo Ejecucion"]
    for x in config.HORIZONTES:
        columnas += [f"MFE ({x} min)", f"Hora MFE ({x} min)", f"MAE pre MFE ({x} min)", f"MAE ({x} min)"]
    return columnas + ["ATR NY hasta la señal", "ATR NY día anterior", "Volumen 1ª hora día anterior"]


def _hora(ns: int) -> float:
    return (ns % _NS_DIA) / _NS_DIA


def _precio(ticks: int | None) -> float | None:
    return None if ticks is None else ticks / config.TICKS_POR_PUNTO


def _celdas(m: Medicion, ctx: Contexto) -> list[tuple[object, str | None]]:
    """Celdas tras las columnas del registro, con su formato."""
    filas: list[tuple[object, str | None]] = [
        (m.revision, None), (_precio(m.precio_op), _FORMATO_PRECIO), (m.ejecucion, None),
    ]
    ejecutada = m.ejecucion == config.EJECUTADA
    filas += [
        (_hora(m.hora_entrada_ns) if ejecutada else None, _FORMATO_HORA),
        (_precio(m.precio_entrada) if ejecutada else None, _FORMATO_PRECIO),
        (m.tiempo_ns / _NS_DIA if ejecutada else None, _FORMATO_DURACION),
    ]
    for x in config.HORIZONTES:
        tramo = m.tramos[x] if ejecutada else None
        filas += [
            (tramo.mfe if tramo else None, None), (_hora(tramo.hora_mfe_ns) if tramo else None, _FORMATO_HORA),
            (tramo.mae_pre_mfe if tramo else None, None), (tramo.mae if tramo else None, None),
        ]
    filas += [
        (None if ctx.atr_senal is None else round(ctx.atr_senal, 2), "0.00"),
        (None if ctx.atr_dia_anterior is None else round(ctx.atr_dia_anterior, 2), "0.00"),
        (ctx.volumen_dia_anterior, "#,##0"),
    ]
    return filas


def escribir_resultados(ruta: Path, por_escenario: dict[int, list[Medicion]], contexto: dict[int, Contexto]) -> None:
    formatos = _formatos_registro()
    encabezados = _encabezados_resultados()
    libro = Workbook()
    libro.remove(libro.active)
    for numero, mediciones in por_escenario.items():
        hoja = libro.create_sheet(f"Escenario {numero}")
        hoja.append(encabezados)
        for celda in hoja[1]:
            celda.font = Font(bold=True)
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = f"A1:{get_column_letter(len(encabezados))}{len(mediciones) + 1}"
        for fila, m in enumerate(mediciones, 2):
            for columna, nombre in enumerate(COLUMNAS, 1):
                celda = hoja.cell(fila, columna, m.senal.crudo[nombre])
                celda.number_format = formatos.get(nombre, "General")
            for columna, (valor, formato) in enumerate(_celdas(m, contexto[m.senal.fila]), len(COLUMNAS) + 1):
                celda = hoja.cell(fila, columna, valor)
                if formato:
                    celda.number_format = formato
        for columna, nombre in enumerate(encabezados, 1):
            hoja.column_dimensions[get_column_letter(columna)].width = max(12, min(len(nombre) + 2, 22))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)


def escribir_analisis(ruta: Path, tablas: list[Tabla]) -> None:
    libro = Workbook()
    libro.remove(libro.active)
    for tabla in tablas:
        hoja = libro.create_sheet(tabla.titulo)
        hoja.append(tabla.encabezados)
        for celda in hoja[1]:
            celda.font = Font(bold=True)
        for fila in tabla.filas:
            hoja.append(fila)
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = f"A1:{get_column_letter(len(tabla.encabezados))}{len(tabla.filas) + 1}"
        for columna, nombre in enumerate(tabla.encabezados, 1):
            hoja.column_dimensions[get_column_letter(columna)].width = max(10, min(len(nombre) + 2, 26))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
