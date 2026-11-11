"""Pestaña "Matriz recomendada" de propuesta_matriz.xlsx: 5 escenarios listos para el simulador.

Los números se leen del catálogo ya medido (analisis_formas.xlsx), así que no hace falta repetir la medición.
"""

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

import config
from simulador.estado_formas import CANDIDATA
from simulador.formas_principal import _RECORRIDO

# (escenario, forma del catálogo, filas del recorrido que cambian, por qué)
ESCENARIOS = [
    ("E1 Referencia", "ATM fijo (referencia)", {},
     "Es la forma base: la de mejor resultado fuera de muestra entre las formas medidas una por una, y contra la que se comparan todas. Si las demás no la superan en semanas nuevas, es la que queda."),
    ("E2 Stop al cierre de vela", "Stop al cierre de vela",
     {"Gestión": "El SL solo se mira al cierre de cada vela: si cierra 180 ticks (90 USD) o más en contra, salir a mercado. El SL de la combinación queda como stop de catástrofe dentro de la vela"},
     "Tiene la segunda mitad más alta de todo el catálogo: aguantó mejor la época floja. Cambia cómo se sale, no qué señales se operan. Su costo es una caída máxima mayor."),
    ("E3 Sin Buy en estructura bajista", "No operar Buy en estructura bajista (B)",
     {"Selección": "No operar Buy cuando la columna M es B (estructura bajista)"},
     "Usa tu propia lectura del mercado (columna M), que decides antes de entrar. Mantiene casi el mismo neto con menos operaciones y mejora la segunda mitad."),
    ("E4 Sin Trend ≥ 2do Pivot", "Dejar de operar Trend ≥ 2do Pivot",
     {"Selección": "No operar la Zona Reacción Trend ≥ 2do Pivot"},
     "Es la zona que salió negativa en todas las mediciones, desde MFE/MAE. Quitarla mantiene el neto, mejora la segunda mitad y baja la caída. Se toma completa y no solo en Te 1, para no afinar con los mismos datos."),
    ("E5 Corte temprano", "Corte temprano: a los 4 min, si va 60 ticks o más en contra, salir",
     {"Gestión": "Si a los 4 minutos va 60 ticks (30 USD) o más en contra, salir a mercado"},
     "Cambia la gestión de las pérdidas: menor caída máxima con un neto parecido. Corta las operaciones que reaccionan en contra antes de llegar al SL."),
]

GENERAL = [
    ("Por qué estos 5", "Cada uno representa un mecanismo distinto: la referencia, otra forma de salir, una selección por tu lectura del mercado, una selección por zona y un corte de pérdidas. Se eligieron entre las Candidatas: positivos en semanas no vistas y en ambas mitades, por encima del 99 % del azar y con una mejora material. Si en semanas nuevas un mecanismo deja de funcionar, los demás permiten verlo."),
    ("Por qué no otros", "Colocar la orden en 100 ms (+4.094 USD) depende de tu velocidad real, no de una regla: primero hay que medirla en el Log de NinjaTrader. La salida parcial requiere 2 contratos. La pausa por las últimas 20 operaciones deja solo 268 operaciones y 6 semanas positivas. Quitar M = A, M = B, I. Fuerte u órdenes lejanas baja el neto más de 700 USD. Las combinaciones entre candidatas todavía no se han medido juntas."),
    ("Cómo pasa al simulador", "Cada escenario se recorre con las 7.744 combinaciones SL/TP, con las mismas reglas de entrada que la referencia. En E2, el SL de cada combinación actúa como stop de catástrofe y el stop al cierre de vela queda fijo en 180 ticks. En E5, el corte a los 4 minutos queda fijo en 60 ticks."),
    ("Cautela", "Son mediciones de 14 semanas. Los 5 escenarios son candidatos, no confirmados: la prueba definitiva son semanas nuevas registradas sin borrar señales. No soy asesor financiero."),
]

_METRICAS = [
    ("Estado", "Estado"), ("Fuera de muestra (USD)", "Fuera: neto (USD)"), ("Profit Factor fuera", "Fuera: PF"),
    ("Operaciones fuera", "Fuera: operaciones"), ("Primera mitad (USD)", "Fuera: primera mitad"), ("Segunda mitad (USD)", "Fuera: segunda mitad"),
    ("Semanas positivas (de 14)", "Fuera: semanas positivas"), ("Caída máxima (USD)", "Caída máxima (USD)"),
    ("Percentil frente al azar", "Percentil frente al azar"), ("ATM o parámetro más elegido", "ATM o parámetro más elegido"),
]


def _catalogo(ruta: Path) -> dict[str, dict]:
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True)["Catálogo"]
    filas = list(hoja.iter_rows(values_only=True))
    encabezados = filas[0]
    return {f[encabezados.index("Forma")]: dict(zip(encabezados, f)) for f in filas[1:]}


def escribir(ruta_analisis: Path = config.REPORTE_FORMAS, ruta_propuesta: Path = config.REPORTE_PROPUESTA_MATRIZ) -> list[str]:
    """Añade (o reemplaza) la pestaña "Matriz recomendada" y marca en "Matriz propuesta" qué columnas entran."""
    catalogo = _catalogo(ruta_analisis)
    faltan = [forma for _, forma, _, _ in ESCENARIOS if forma not in catalogo]
    if faltan:
        raise ValueError(f"Formas que no están en el catálogo: {faltan}")
    libro = openpyxl.load_workbook(ruta_propuesta)
    if "Matriz recomendada" in libro.sheetnames:
        del libro["Matriz recomendada"]
    hoja = libro.create_sheet("Matriz recomendada", 0)
    negrita = Font(bold=True)
    ajuste = Alignment(wrap_text=True, vertical="top")
    hoja.append(["Recorrido", *[e[0] for e in ESCENARIOS]])
    for nombre, valor in _RECORRIDO:
        hoja.append([nombre, *[cambios.get(nombre, valor) for _, _, cambios, _ in ESCENARIOS]])
    for etiqueta, columna in _METRICAS:
        hoja.append([etiqueta, *[catalogo[forma][columna] for _, forma, _, _ in ESCENARIOS]])
    hoja.append(["Por qué este escenario", *[porque for *_, porque in ESCENARIOS]])
    hoja.append([])
    no_candidatas = [nombre for nombre, forma, _, _ in ESCENARIOS if catalogo[forma]["Estado"] != CANDIDATA]
    general = list(GENERAL)
    if no_candidatas:
        general.insert(0, ("Aviso", f"Con los criterios actuales, {' y '.join(no_candidatas)} ya no {'son' if len(no_candidatas) > 1 else 'es'} {CANDIDATA} (ver su motivo en resumen_escenarios.xlsx). "
                                    "Esta Matriz recomendada se revisa contigo antes de aprobarla."))
    for titulo, texto in general:
        hoja.append([titulo, texto])
        hoja.merge_cells(start_row=hoja.max_row, start_column=2, end_row=hoja.max_row, end_column=len(ESCENARIOS) + 1)
    for celda in hoja[1]:
        celda.font = negrita
    for fila in hoja.iter_rows(min_row=2):
        fila[0].font = negrita
        for celda in fila:
            celda.alignment = ajuste
    for fila in hoja.iter_rows(min_row=len(_RECORRIDO) + 2, max_row=len(_RECORRIDO) + 1 + len(_METRICAS)):
        for celda in fila[1:]:
            if isinstance(celda.value, (int, float)) and celda.value != 0 and "Percentil" not in str(fila[0].value) and "Operaciones" not in str(fila[0].value) and "Semanas" not in str(fila[0].value) and "Profit" not in str(fila[0].value) and "Caída" not in str(fila[0].value):
                celda.fill = PatternFill("solid", fgColor="C6EFCE" if celda.value > 0 else "FFC7CE")
    hoja.column_dimensions["A"].width = 30
    for letra in "BCDEF":
        hoja.column_dimensions[letra].width = 42
    hoja.freeze_panes = "B2"

    propuesta = libro["Matriz propuesta"]
    columnas = [c.value for c in propuesta[1]]
    elegidas = {f"Referencia + {forma}": nombre for nombre, forma, _, _ in ESCENARIOS[1:]}
    elegidas["Referencia"] = ESCENARIOS[0][0]
    marca = ["¿En la Matriz recomendada?", *[elegidas.get(c, "No") for c in columnas[1:]]]
    if propuesta.cell(propuesta.max_row, 1).value == marca[0]:
        propuesta.delete_rows(propuesta.max_row)
    propuesta.append(marca)
    propuesta.cell(propuesta.max_row, 1).font = negrita
    libro.save(ruta_propuesta)
    return [e[0] for e in ESCENARIOS]
