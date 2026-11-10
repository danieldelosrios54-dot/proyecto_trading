"""Archivos Excel de resultado de la validación."""

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

import config
from validacion.modelos import Motivo, Senal, estado, hora_texto
from validacion.ticks import ResultadoFecha, estado_fecha

_ESTADOS = (config.INVALIDA, config.NOTIFICADA, config.VALIDA)
_SIN = {
    config.INVALIDA: "Sin señales Invalidas",
    config.NOTIFICADA: "Sin señales validas con notificación",
}


def _hoja(libro: Workbook, titulo: str, encabezados: list[str], filas: list[list], anchos: list[int]) -> None:
    hoja = libro.create_sheet(titulo)
    hoja.append(encabezados)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    hoja.freeze_panes = "A2"
    for fila in filas:
        hoja.append(fila)
    for columna, ancho in zip("ABCDEFGHIJ", anchos):
        hoja.column_dimensions[columna].width = ancho


def _resumen(libro: Workbook, filas: list[list]) -> None:
    hoja = libro.active
    hoja.title = "Resumen"
    for fila in filas:
        hoja.append(fila)
    for fila in hoja.iter_rows():
        if fila[0].value and fila[0].value.startswith("Total"):
            fila[0].font = Font(bold=True)
    hoja.column_dimensions["A"].width = 44
    hoja.column_dimensions["B"].width = 12


def _conteo(senales: list[Senal], motivos: dict[int, list[Motivo]]) -> Counter:
    return Counter(estado(motivos[s.fila]) for s in senales)


def _hojas_senales(libro: Workbook, senales: list[Senal], motivos: dict[int, list[Motivo]]) -> None:
    def texto(s: Senal) -> str:
        return " | ".join(str(m) for m in motivos[s.fila])

    for estado_lista, titulo in ((config.INVALIDA, "Invalidas"), (config.NOTIFICADA, "Con notificacion")):
        filas = [[s.id, texto(s)] for s in senales if estado(motivos[s.fila]) == estado_lista]
        _hoja(libro, titulo, ["ID", "Motivo"], filas or [[_SIN[estado_lista], ""]], [40, 110])
    filas = [
        [s.id, s.fila, s.fecha.isoformat() if s.fecha else None, estado(motivos[s.fila]), texto(s)]
        for s in sorted(senales, key=lambda s: (s.id is None, s.id))
    ]
    _hoja(libro, "Estado por señal", ["ID", "Fila Excel", "Fecha", "Estado", "Motivos"], filas, [8, 11, 12, 24, 110])


def reporte_senales(ruta: Path, senales: list[Senal], motivos: dict[int, list[Motivo]]) -> None:
    conteo = _conteo(senales, motivos)
    libro = Workbook()
    _resumen(libro, [["Total señales registradas", len(senales)], *[[e, conteo[e]] for e in _ESTADOS]])
    _hojas_senales(libro, senales, motivos)
    _guardar(libro, ruta)


def reporte_ticks(
    ruta: Path,
    senales: list[Senal],
    motivos: dict[int, list[Motivo]],
    resultados: dict[str, ResultadoFecha],
    mediana: float,
    senales_por_incidente: dict[tuple[str, int], int],
) -> None:
    fechas = Counter(estado_fecha(r) for r in resultados.values())
    senal_conteo = _conteo(senales, motivos)
    libro = Workbook()
    _resumen(libro, [
        ["Total fechas de las señales registradas", len(resultados)],
        *[[e, fechas[e]] for e in _ESTADOS],
        [],
        ["Total señales registradas", len(senales)],
        *[[e, senal_conteo[e]] for e in _ESTADOS],
    ])
    _hojas_senales(libro, senales, motivos)

    por_regla = lambda r, regla: sum(1 for i in r.incidentes if i.regla == regla)
    _hoja(
        libro, "Detalle por fecha",
        ["Fecha", "Estado", "Ticks", "Volumen", "% mediana", "Saltos T9", "Huecos T10", "Huecos T11", "Motivos de toda la fecha"],
        [[
            r.fecha.isoformat(), estado_fecha(r), r.ticks, r.volumen,
            round(100 * r.volumen / mediana, 1) if mediana else None,
            por_regla(r, "T9"), por_regla(r, "T10"), por_regla(r, "T11"),
            " | ".join(str(m) for m in r.motivos),
        ] for r in sorted(resultados.values(), key=lambda r: r.clave)],
        [12, 24, 11, 11, 10, 10, 10, 10, 80],
    )
    _hoja(
        libro, "Incidentes",
        ["Fecha", "Regla", "Inicio (UTC)", "Fin (UTC)", "Duración (s)", "Salto (ticks)", "Pausa previa (ms)", "Volumen del tick", "Señales con esto en su tramo"],
        [[
            r.fecha.isoformat(), i.regla, hora_texto(i.inicio_ns), hora_texto(i.fin_ns),
            round(i.segundos, 3), i.ticks, i.pausa_ms, i.volumen,
            senales_por_incidente.get((i.regla, i.inicio_ns), 0),
        ] for r in sorted(resultados.values(), key=lambda r: r.clave) for i in r.incidentes],
        [12, 7, 14, 14, 12, 12, 16, 15, 26],
    )
    _guardar(libro, ruta)


def _guardar(libro: Workbook, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
