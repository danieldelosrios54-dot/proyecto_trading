"""Ejecuta el simulador completo y escribe los 4 archivos."""

import json
import time
from collections import Counter
from datetime import date

import numpy as np
import polars as pl

import config
from medicion.analisis import Medicion, Tabla
from medicion.entrada import Dia
from simulador import metricas as mt
from simulador.analisis import Analisis
from simulador.datos import Conjunto, calendario, conjunto, operaciones_de
from simulador.indicadores import SerieIndicadores, indicadores_serie, rango_verdadero, valor_en
from simulador.operaciones import lunes
from simulador.reportes import escribir_libro, tabla_combinaciones
from simulador.velas_sesion import NOMBRE_REGISTRO as REGISTRO_VELAS
from simulador.velas_sesion import cargar_velas
from validacion.extraccion import NOMBRE_REGISTRO as REGISTRO_TICKS
from validacion.modelos import Senal, clave_fecha

_NS_MINUTO = 60_000_000_000
_REFERENCIA = "ATR NY desde la apertura (referencia)"
_MINUTOS = "Minutos desde la apertura"


def _serie_de_dia() -> dict[str, int]:
    """Serie de velas (contrato) de cada fecha, según el archivo del que salieron sus ticks."""
    ticks = json.loads((config.CARPETA_TICKS_EXTRAIDOS / REGISTRO_TICKS).read_text(encoding="utf-8"))
    velas = json.loads((config.CARPETA_VELAS_SESION / REGISTRO_VELAS).read_text(encoding="utf-8"))
    return {fecha: velas["series"][archivo] for archivo, e in ticks["archivos"].items() for fecha in e["fechas_extraidas"]}


def _indicadores(c: Conjunto, velas: pl.DataFrame, series: dict[int, dict[int, SerieIndicadores]], serie_de_dia: dict[str, int], atr_ny: dict[int, float | None], dias: dict[str, Dia]) -> dict[str, np.ndarray]:
    nombres = list(next(iter(series[1].values())).valores)
    salida = {n: np.full(len(c), np.nan) for n in [*nombres, _REFERENCIA, _MINUTOS]}
    for k, op in enumerate(c.ops):
        valores = valor_en(series[op.te][serie_de_dia[op.clave_dia]], op.hora_utc_ns)
        for n in nombres:
            salida[n][k] = valores[n]
        referencia = atr_ny.get(op.fila)
        salida[_REFERENCIA][k] = np.nan if referencia is None else referencia / config.TICKS_POR_PUNTO
        salida[_MINUTOS][k] = (op.hora_utc_ns - dias[op.clave_dia].apertura_ns) / _NS_MINUTO
    return salida


def _atr_en_apertura(velas: pl.DataFrame, series1: dict[int, SerieIndicadores], serie_de_dia: dict[str, int], dias: dict[str, Dia], velas_max: int = 30) -> list[list]:
    """Cuánto se parece el ATR(5) y ATR(10) de NinjaTrader al ATR NY en cada vela tras la apertura."""
    tr_por_serie = {}
    for (serie,), g in velas.group_by(["serie"], maintain_order=True):
        tr_por_serie[serie] = rango_verdadero(*(g[k].to_numpy().astype(np.float64) for k in ("high", "low", "close")))
    r5 = {k: [] for k in range(1, velas_max + 1)}
    r10 = {k: [] for k in range(1, velas_max + 1)}
    for clave, dia in dias.items():
        s = serie_de_dia.get(clave)
        if s is None:
            continue
        ind, tr = series1[s], tr_por_serie[s]
        i0 = int(np.searchsorted(ind.cierre_ns, dia.apertura_ns + _NS_MINUTO))
        for k in range(1, velas_max + 1):
            i = i0 + k - 1
            if i >= len(ind.cierre_ns) or ind.cierre_ns[i] != dia.apertura_ns + k * _NS_MINUTO:
                break
            ny = tr[i0:i + 1].mean() / config.TICKS_POR_PUNTO
            if ny > 0:
                r5[k].append(ind.valores["ATR (5)"][i] / ny)
                r10[k].append(ind.valores["ATR (10)"][i] / ny)
    filas = []
    for k in range(1, velas_max + 1):
        a, b = np.array(r5[k]), np.array(r10[k])
        if not len(a):
            continue
        filas.append([k, len(a), round(float(np.median(a)), 2), round(float(np.median(b)), 2), round(100 * float((np.abs(a - 1) <= 0.2).mean()), 1), round(100 * float((np.abs(b - 1) <= 0.2).mean()), 1)])
    return filas


def _conteos(mediciones: list[Medicion], filtro) -> tuple[int, int]:
    """(Revisión inválida, no ejecutadas) entre las señales que cumplen el filtro."""
    invalidas = sum(1 for m in mediciones if filtro(m) and m.revision != config.REVISION_VALIDA)
    no_ej = sum(1 for m in mediciones if filtro(m) and m.revision == config.REVISION_VALIDA and m.ejecucion != config.EJECUTADA)
    return invalidas, no_ej


def _titulo_zona(zona: str, senales: int) -> str:
    titulo = zona.replace("/", "-")
    return f"{titulo} (poca muestra)" if senales < config.MUESTRA_MINIMA else titulo


def _como_leer(tablas: dict[str, Tabla]) -> Tabla:
    def fila(titulo: str, condicion) -> list | None:
        t = tablas.get(titulo)
        return next((f for f in t.filas if condicion(f)), None) if t else None

    def num(x) -> str:
        return "—" if x is None else (f"{x:,.2f}" if isinstance(x, float) else str(x))

    v = config.VELAS_ENTREGABLES
    p1 = fila("P1 Cierre por tiempo", lambda f: f[0] == 1 and f[1] == v and f[2] == "Todas")
    p5 = fila("P5 Breakeven", lambda f: f[0] == v and str(f[1]).startswith("Breakeven en +40"))
    p7 = fila("P7 Reglas del día", lambda f: str(f[0]).startswith("Dejar de operar al perder 50"))
    rec = tablas["P8 Recomendación"].filas[0] if tablas.get("P8 Recomendación") and tablas["P8 Recomendación"].filas else None
    filas = [
        ["Todas", "Reglas generales", "Dentro = se elige la combinación mirando las 14 semanas (lo que muestra un backtest normal). Fuera = se elige con 13 semanas y se mide en la que no se vio, 14 veces: lo más parecido a operar en vivo. Mejor zona = la combinación cuyo promedio con sus vecinas (±3 USD) es el más alto, para no premiar una combinación suelta. USD por 1 contrato MNQ con comisión y deslizamientos.", ""],
        ["P1 Cierre por tiempo", "¿Qué cierre por tiempo (3 a 10 velas) da más combinaciones positivas? Incluye Te 1, Te 2, Buy y Sell del Escenario 1.",
         "Cada fila es un escenario y un cierre. Combinaciones positivas: de las 7.744, cuántas ganaron. Positivas en ambas mitades: ganaron en las primeras 7 semanas y también en las últimas 7.",
         f"Escenario 1 con {v} velas: {num(p1[3])} combinaciones positivas ({num(p1[4])} %), {num(p1[5])} en ambas mitades; fuera de muestra {num(p1[12])} USD." if p1 else ""],
        ["P2 Cierre por zona", "Lo mismo para cada Zona Reacción, medida sola (sin solapamiento). Al final, si conviene un ATM por zona o uno para todas.",
         "Las zonas marcadas con poca muestra tienen menos de 30 señales: sus resultados pueden ser azar.", ""],
        ["P3 Cierre por semana", "Cómo cambian las combinaciones cada semana.", "Mejor = la combinación con más neto esa semana; cambia de semana a semana.", ""],
        ["P3 Indicadores tramos", "Con el indicador en tramo bajo, medio o alto, ¿qué combinación conviene?", "Desde y Hasta están en las unidades que ves en NinjaTrader (puntos para ATR, Range y rangos del día).", ""],
        ["P3 Indicadores fuera", "¿Elegir la combinación según el indicador funciona en semanas no vistas?", "Sirve solo si gana al ATM único fuera de muestra y supera al 95 % de tramos inventados al azar.", ""],
        ["P3 ATR en la apertura", "¿Desde qué vela el ATR(5) y ATR(10) reflejan la volatilidad de la apertura?", "1 = igual al ATR NY. Menos de 1 = el ATR se queda corto por las velas tranquilas del premercado.", ""],
        ["P4 Escenarios", "¿Qué escenario da más combinaciones positivas y cuánto cuesta cada cambio?", "Diferencia negativa = el cambio empeora frente al Escenario 1.", ""],
        ["P5 Breakeven", "¿Conviene pasar el SL a la entrada?", "% cerradas en breakeven: operaciones que terminaron en la entrada en la combinación típica.",
         f"Con {v} velas y breakeven en +40: {num(p5[2])} combinaciones positivas; veredicto: {p5[-1]}" if p5 else ""],
        ["P6 SL por tiempo", "¿Conviene acercar el SL al cerrar cada vela?", "Ejemplo de la regla: SL 90 USD con 6 velas pasa a 75, 60, 45, 30 y 15 USD.", ""],
        ["P7 Reglas del día", "¿Qué reglas del día mejoran el resultado?", "Todas parten del ATM fijo elegido fuera de muestra con 4 velas. Añade valor = más neto y mejor última mitad que la base.",
         f"Dejar de operar al perder 50 USD: {num(p7[1])} USD fuera de muestra; ¿añade valor? {p7[-1]}" if p7 else ""],
        ["P8 Recomendación", "Todas las formas medidas, ordenadas por resultado fuera de muestra.", "Candidata = positiva fuera de muestra y en ambas mitades. Confirmada = además supera al 95 % de las carteras al azar. Validada = se sostiene en semanas nuevas (aún no hay).",
         f"Primera de la lista: {rec[0]}, {num(rec[5])} USD fuera de muestra, nivel {rec[-3]}." if rec else ""],
        ["Ratios", "¿Funciona mejor TP menor, igual o mayor que el SL?", "Ratio = TP / SL.", ""],
        ["Otras salidas", "Salidas propuestas por el analista: parcial, trailing, stop al cierre de vela, salir si no reacciona.", "Compáralas con la primera fila de cada cierre: SL/TP fijos con la misma cuadrícula gruesa.", ""],
        ["Por qué cambian los días", "¿Qué indicador anticipa días de más recorrido a favor (MFE) y más en contra (MAE pre MFE)?", "Relación de 0 (ninguna) a 1 (total). Sobre 0,3 es una relación útil.", ""],
        ["Validación", "¿Los resultados son de tus señales o del azar?", "Percentil 95 o más = mejor que el 95 % de las alternativas al azar.", ""],
    ]
    return Tabla("Cómo leer", ["Pestaña", "Qué responde", "Cómo leer", "Ejemplo con tus datos"], filas)


def ejecutar(senales: list[Senal], mediciones: dict[int, list[Medicion]], dias: dict[str, Dia], atr_ny: dict[int, float | None], avisar=print) -> dict:
    inicio = time.time()
    cal = calendario(mediciones[1], dias)
    nsem = len(cal.semanas)
    conjuntos = {e: conjunto(operaciones_de(mediciones[e], dias), dias, cal) for e in mediciones}
    analisis = Analisis(conjuntos, nsem, cal.zonas, cal.semanas, dias, avisar)

    avisar("Simulando Escenario 1 (cierres, gestiones y otras salidas)...")
    analisis.escenario1()
    avisar("Simulando Escenarios 2 a 4...")
    analisis.escenarios()
    avisar("Reglas del día...")
    analisis.reglas_dia()

    avisar("Velas de sesión e indicadores de NinjaTrader...")
    velas = cargar_velas(config.CARPETA_DATA_TICKS, config.CARPETA_VELAS_SESION, avisar)
    series = {te: indicadores_serie(velas, te) for te in config.VALORES_TE}
    serie_de_dia = _serie_de_dia()
    c1 = conjuntos[1]
    valores_ind = _indicadores(c1, velas, series, serie_de_dia, atr_ny, dias)
    analisis.indicadores(valores_ind, _atr_en_apertura(velas, series[1], serie_de_dia, dias))
    avisar("Validación (azar, inversa, grupos falsos, PBO)...")
    analisis.validacion(cal)
    analisis.recomendacion()

    avisar("Escribiendo archivos...")
    fechas = [date(int(d[:4]), int(d[4:6]), int(d[6:])) for d in cal.dias]
    ndias = len(cal.dias)

    def columnas(c: Conjunto, m, tomada, filas, med: list[Medicion], filtro, con_solape: bool) -> dict:
        invalidas, no_ej = _conteos(med, filtro)
        return mt.columnas(m.valores[filas], m.salida_ns[filas], tomada[filas], c.entrada_ns[filas], c.hora_utc_ns[filas], c.dia[filas], ndias, invalidas, no_ej, con_solape)

    todas = []
    for e, c in conjuntos.items():
        m, t = analisis.k4[e]
        filas = np.arange(len(c))
        todas.append(tabla_combinaciones(f"Escenario {e}", columnas(c, m, t, filas, mediciones[e], lambda x: True, True), config.SIM_TICKS, config.USD_POR_TICK, fechas))
    escribir_libro(config.REPORTE_TODAS, todas)

    m, t = analisis.k4[1]
    unos = np.ones_like(t)
    zonas = []
    for z, zona in enumerate(cal.zonas):
        filas = np.flatnonzero(c1.zona == z)
        zonas.append(tabla_combinaciones(_titulo_zona(zona, len(filas)), columnas(c1, m, unos, filas, mediciones[1], lambda x, zona=zona: str(x.senal.zona) == zona, False), config.SIM_TICKS, config.USD_POR_TICK, fechas))
    escribir_libro(config.REPORTE_ZONAS, zonas)

    semanas = []
    for w, lun in enumerate(cal.semanas):
        filas = np.flatnonzero(c1.semana == w)
        semanas.append(tabla_combinaciones(f"Semana {lun}", columnas(c1, m, t, filas, mediciones[1], lambda x, lun=lun: x.senal.fecha is not None and lunes(x.senal.fecha) == lun, True), config.SIM_TICKS, config.USD_POR_TICK, fechas))
    por_fila = {s.fila: s for s in senales}
    nombres = list(valores_ind)
    filas_ind = []
    for k, op in enumerate(c1.ops):
        s = por_fila[op.fila]
        hora = (op.hora_utc_ns % mt.NS_DIA) / mt.NS_DIA
        filas_ind.append([s.id, s.fecha, str(op.semana), op.zona, op.tipo, op.te, hora, *[valores_ind[n][k] for n in nombres]])
    semanas.append(Tabla("Indicadores por señal", ["ID", "Fecha", "Semana (lunes)", "Zona Reacción", "Tipo", "Te", "Hora UTC", *nombres], filas_ind))
    resumen = []
    for w, lun in enumerate(cal.semanas):
        filas = c1.semana == w
        resumen.append([str(lun), int(filas.sum()), *[None if np.all(np.isnan(valores_ind[n][filas])) else round(float(np.nanmean(valores_ind[n][filas])), 2) for n in nombres]])
    semanas.append(Tabla("Resumen semanal", ["Semana (lunes)", "Señales", *[f"{n} (promedio)" for n in nombres]], resumen))
    escribir_libro(config.REPORTE_SEMANAS, semanas)

    orden = [
        "P8 Recomendación", "P1 Cierre por tiempo", "P2 Cierre por zona", "P3 Cierre por semana", "P3 Indicadores tramos",
        "P3 Indicadores fuera", "P3 ATR en la apertura", "P4 Escenarios", "P5 Breakeven", "P6 SL por tiempo", "P7 Reglas del día",
        "Ratios", "Otras salidas", "Por qué cambian los días", "Validación",
    ]
    escribir_libro(config.REPORTE_ANALISIS_COMBINACIONES, [_como_leer(analisis.tablas), *[analisis.tablas[n] for n in orden]])

    niveles = Counter(f[-3] for f in analisis.tablas["P8 Recomendación"].filas)
    return {"segundos": time.time() - inicio, "ejecutadas": {e: len(c) for e, c in conjuntos.items()}, "niveles": dict(niveles)}
