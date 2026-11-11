"""Ejecuta el catálogo del documento 5, asigna el estado de cada forma y escribe los dos archivos."""

import time
from collections import defaultdict

import numpy as np

import config
from medicion.analisis import Tabla
from simulador import salidas
from simulador.estado_formas import CANDIDATA, ESTADOS, NO_MEDIDA, decidir
from simulador.formas import REF, Catalogo, base
from simulador.datos import calendario
from simulador.reportes import escribir_libro

PREGUNTAS = {
    "1": "¿Operar con ATM fijo, o ajustar a breakeven o mover el SL?",
    "2": "¿Operar con o sin solapamiento?",
    "3": "¿Operar con un ATM para cada Zona Reacción?",
    "4": "¿Dejar de operar alguna Zona Reacción, o alguna en un Te?",
    "5": "¿Cambiar de ATM según un indicador o según la semana?",
    "6": "¿Qué cierre por tiempo usar?",
    "7": "¿Qué distancia operativa usar para la orden pendiente?",
    "8": "¿Cómo cambia el resultado con el tiempo de colocación?",
    "9": "¿Qué ventana de ejecución usar?",
    "10": "¿Evitar deslizamientos o ajustar el SL y el TP?",
    "11": "¿Stop límite o stop a mercado?",
    "12": "¿Qué Zona Reacción priorizar si entran varias a la vez?",
    "13": "¿Priorizar Buy o Sell si entran varias a la vez?",
    "14": "¿No operar en noticias?",
    "15": "¿Descartar Buy o Sell según el mercado?",
    "16": "¿Vigilar cuándo una combinación pierde ventaja?",
    "Nueva": "Formas nuevas propuestas por el analista",
}
NO_MEDIBLE_PARCIAL = {
    "2": "Compras y ventas abiertas a la vez exigen dos cuentas en NinjaTrader: Descartada.",
    "9": "Alargar la ventana no se puede medir: faltan las señales que se borraban.",
    "15": "La volatilidad implícita (VIX/VXN) no se midió: falta descargarla.",
}
_RECORRIDO = [
    ("Revisión", "Igual"),
    ("Calcular el precio de la orden pendiente", f'"OHLC" ± {REF[0]} ticks'),
    ("Colocación de la orden pendiente", f"00:00:00.{REF[1]:03d}"),
    ("Re-entrada", f"Máximo {config.LIMITE_REENTRADA_PRINCIPAL} ticks a favor antes de volver"),
    ("Ventana de ejecución", "Igual (1 vela impulso, 2 velas continuación)"),
    ("Disparo de la orden pendiente", "Stop a mercado, primer Last"),
    ("Deslizamiento de entrada", f"± {REF[2]} ticks"),
    ("ATM", "Fijo: un SL y un TP"),
    ("Gestión", "Sin cambios del SL"),
    ("Cierre por tiempo", f"{REF[3]} minutos desde la entrada"),
    ("Disparo del cierre", "SL, TP o tiempo"),
    ("Deslizamiento de salida", "TP al precio (pasando 2 ticks); SL al precio − 2; tiempo − 2"),
    ("Solapamiento", "1 posición a la vez"),
    ("Prioridad", "Primera del registro"),
    ("Selección", "Todas las señales"),
    ("Tamaño", "1 contrato"),
    ("Comisión", "1,86 USD por operación"),
]


def _fila_metricas(ev) -> list:
    if ev is None:
        return [None] * 11
    f, d = ev.fuera, ev.dentro
    return [round(d.neto, 2), round(d.pf, 2), round(f.neto, 2), round(f.pf, 2), f.operaciones, f.semanas_positivas, round(f.mitad1, 2), round(f.mitad2, 2),
            None if np.isnan(ev.caida) else round(ev.caida, 2), None if ev.vecinas is None else round(ev.vecinas, 2), ev.elegida]


_ENC_METRICAS = ["Dentro: neto (USD)", "Dentro: PF", "Fuera: neto (USD)", "Fuera: PF", "Fuera: operaciones", "Fuera: semanas positivas",
                 "Fuera: primera mitad", "Fuera: segunda mitad", "Caída máxima (USD)", "Combinaciones Vecinas", "ATM o parámetro más elegido"]


def _rangos(valores) -> str:
    v = sorted(set(valores))
    return f"{v[0]}–{v[-1]}" if len(v) > 1 and isinstance(v[0], (int, float)) else " / ".join(str(x) for x in v)


def ejecutar_formas(senales, mediciones, dias, medir, atr_ny, avisar=print) -> dict:
    inicio = time.time()
    salidas.SL_AL_PRECIO = True
    cal = calendario(mediciones, dias)
    cat = Catalogo(base(mediciones, dias, cal), dias, cal, senales, medir, atr_ny, avisar)
    for paso, funcion in (("ATM fijo y gestión", cat.gestion), ("Solapamiento", cat.solapamiento), ("Grupos y columna M", cat.grupos),
                          ("Mercado e indicadores", cat.mercado), ("Ejecución", cat.ejecucion), ("Noticias", cat.noticias), ("Formas sin datos", cat.no_medidas), ("Mapa de reglas", cat.mapa_reglas)):
        avisar(f"Midiendo: {paso}...")
        funcion()
    avisar("Comparando con el azar...")
    azar = cat.azar()
    mediana_azar = float(np.median(azar))

    for f in cat.filas:
        if f.ev is not None:
            f.estado, f.argumento = decidir(f.ev, cat.ref, mediana_azar, f.forma == "ATM fijo (referencia)")
            if f.forzado:
                datos = f.argumento[f.argumento.find("Fuera de muestra"):]
                f.estado, f.argumento = f.forzado, f"{f.nota} {datos}".strip()
    filas_mapa = []
    for d, ms, minutos, zonas, n, ev in cat.mapa:
        es_ref = (d, ms, minutos, zonas) == (REF[0], REF[1], REF[3], "Todas")
        estado, argumento = decidir(ev, cat.ref, mediana_azar, es_ref)
        filas_mapa.append([d, ms, minutos, zonas, n, *_fila_metricas(ev), round(100 * float((azar < ev.fuera.neto).mean())), estado, argumento])

    # Conclusiones por punto
    por_punto = defaultdict(list)
    for f in cat.filas:
        por_punto[f.punto].append(f)
    for fila in filas_mapa:
        d, ms, minutos, zonas = fila[:4]
        if ms == REF[1] and minutos == REF[3] and zonas == "Todas":
            por_punto["7"].append(("mapa", f"Distancia {d} ticks", fila))
        if d == REF[0] and minutos == REF[3] and zonas == "Todas":
            por_punto["8"].append(("mapa", f"Colocación {ms} ms", fila))
        if d == REF[0] and ms == REF[1] and zonas == "Todas":
            por_punto["6"].append(("mapa", f"Cierre a {minutos} min", fila))
    conclusiones = []
    for punto, pregunta in PREGUNTAS.items():
        elementos = por_punto.get(punto, [])
        estados = defaultdict(list)
        for e in elementos:
            nombre, estado = (e[1], e[2][-2]) if isinstance(e, tuple) else (e.forma, e.estado)
            estados[estado].append(nombre)
        medible = [e for e in elementos if not (not isinstance(e, tuple) and e.estado == NO_MEDIDA)]
        estado_punto = "No medido" if not medible else ("Parcial" if punto in NO_MEDIBLE_PARCIAL else "Medido")
        respuesta = " · ".join(f"{k} ({len(v)}): {'; '.join(v[:6])}{'…' if len(v) > 6 else ''}" for k, v in ((k, estados[k]) for k in ESTADOS) if v)
        nota = NO_MEDIBLE_PARCIAL.get(punto, "")
        conclusiones.append([punto, pregunta, estado_punto, respuesta, nota])

    catalogo = [[f.punto, f.grupo, f.forma, f.contratos, *_fila_metricas(f.ev),
                 None if f.ev is None else round(100 * float((azar < f.ev.fuera.neto).mean())), f.estado, f.argumento, f.nota] for f in cat.filas]
    enc_cat = ["Punto", "Grupo", "Forma", "Contratos", *_ENC_METRICAS, "Percentil frente al azar", "Estado", "Argumento", "Nota"]
    tablas = [
        Tabla("Conclusiones", ["Punto", "Pregunta", "Estado del punto", "Formas por estado", "Lo que no se pudo medir"], conclusiones),
        Tabla("Catálogo", enc_cat, catalogo),
        Tabla("Mapa de reglas", ["Distancia (ticks)", "Colocación (ms)", "Cierre (min)", "Zonas", "Operaciones ejecutables", *_ENC_METRICAS, "Percentil frente al azar", "Estado", "Argumento"], filas_mapa),
    ]
    for grupo in ("Entrada", "Salida", "Selección", "Posición", "Adaptación"):
        tablas.append(Tabla(grupo, enc_cat, [r for r in catalogo if r[1] == grupo]))
    tablas.append(Tabla("Validación", ["Prueba", "Valor"], [
        ["Carteras al azar (misma hora de otro día, dirección al azar)", config.FORMAS_AZAR],
        ["Azar fuera de muestra: p5 / mediana / p95 (USD)", " / ".join(f"{x:,.0f}" for x in np.percentile(azar, [5, 50, 95]))],
        ["Referencia fuera de muestra (USD)", round(cat.ref.fuera.neto, 2)],
    ]))
    tablas.append(_como_leer())
    colores = {t.titulo: {"Fuera: neto (USD)", "Fuera: segunda mitad"} for t in tablas}
    escribir_libro(config.REPORTE_FORMAS, tablas, colores)

    # Propuesta de Matriz
    candidatas = [f for f in cat.filas if f.estado == CANDIDATA]
    columnas = []
    referencia = next((f for f in candidatas if f.forma == "ATM fijo (referencia)"), None)
    if referencia:
        columnas.append(("Referencia", {}, referencia.argumento))
    mapa_cand = [r for r in filas_mapa if r[-2] == CANDIDATA]
    if mapa_cand:
        cambio = {"Calcular el precio de la orden pendiente": f'"OHLC" ± {_rangos([r[0] for r in mapa_cand])} ticks',
                  "Colocación de la orden pendiente": f"{_rangos([r[1] for r in mapa_cand])} ms", "Cierre por tiempo": f"{_rangos([r[2] for r in mapa_cand])} minutos",
                  "Selección": _rangos([r[3] for r in mapa_cand])}
        columnas.append((f"Mapa de reglas ({len(mapa_cand)} combinaciones candidatas)", cambio, "Ver la pestaña Mapa candidatas: cada combinación de reglas con su argumento."))
    for f in candidatas:
        if f is not referencia:
            columnas.append((f"Referencia + {f.forma}", f.cambio, f.argumento))
    filas_matriz = []
    for nombre, valor in _RECORRIDO:
        filas_matriz.append([nombre, *[c[1].get(nombre, valor) for c in columnas]])
    filas_matriz.append(["Argumento", *[c[2] for c in columnas]])
    propuesta = [Tabla("Matriz propuesta", ["Recorrido", *[c[0] for c in columnas]], filas_matriz),
                 Tabla("Mapa candidatas", ["Distancia (ticks)", "Colocación (ms)", "Cierre (min)", "Zonas", "Operaciones ejecutables", *_ENC_METRICAS, "Percentil frente al azar", "Estado", "Argumento"], mapa_cand)]
    from simulador.resumen_escenarios import COLORES, tablas as tablas_resumen
    mapa_completo = [(d, ms, minutos, zonas, ev, fila[-2], fila[-1]) for (d, ms, minutos, zonas, _, ev), fila in zip(cat.mapa, filas_mapa)]
    resumen = tablas_resumen(cat.filas, mapa_completo, cat.ref.fuera.neto, cat.ref.top, avisar)
    escribir_libro(config.REPORTE_RESUMEN_ESCENARIOS, resumen, {"Resumen escenarios": COLORES})
    escribir_libro(config.REPORTE_PROPUESTA_MATRIZ, propuesta)
    from simulador.matriz_recomendada import escribir as escribir_recomendada
    escribir_recomendada()
    salidas.SL_AL_PRECIO = False

    cuenta = defaultdict(int)
    for f in cat.filas:
        cuenta[f.estado] += 1
    return {"Segundos": round(time.time() - inicio), "Formas por estado": dict(cuenta), "Mapa: candidatas": len(mapa_cand),
            "Referencia fuera de muestra (USD)": round(cat.ref.fuera.neto, 2), "Mediana del azar (USD)": round(mediana_azar, 2)}


def _como_leer() -> Tabla:
    return Tabla("Cómo leer", ["Concepto", "Explicación"], [
        ["Objetivo", "No se busca la mejor forma ni optimizar. Cada forma se mide igual y se le asigna un estado con su argumento en números."],
        ["Referencia", f"Orden a ±{REF[0]} ticks, colocación en {REF[1]} ms, deslizamiento de {REF[2]}, cierre a {REF[3]} minutos, ATM fijo. Cada forma cambia solo lo que define."],
        ["Dentro", "Eligiendo el ATM (o parámetro) con las 14 semanas y midiendo en las mismas."],
        ["Fuera", "Eligiendo con 13 semanas y midiendo en la que falta, 14 veces: lo más parecido a operar en vivo."],
        [CANDIDATA, "Positiva fuera de muestra y en ambas mitades, mejor que la mediana del azar, da valor (mejora el neto, la segunda mitad, la caída máxima o las semanas positivas sin empeorar con claridad frente a la referencia) y la proporción de sus combinaciones positivas que gana también en ambas mitades no es menor que la de la referencia."],
        ["En observación", "Positiva fuera de muestra, pero una mitad es negativa, no supera al azar o una proporción menor que la referencia de sus combinaciones positivas gana en ambas mitades (depende más de una época)."],
        ["Descartada", "Negativa fuera de muestra; positiva sin dar valor; requiere 2 cuentas (compras y ventas abiertas a la vez); o la medición tiene un sesgo (por ejemplo, salir con la señal contraria)."],
        ["No Aplica", "No es una decisión sino un costo (por ejemplo, el deslizamiento): muestra cuánto cambia el resultado."],
        ["No Medida", "Falta un dato para medirla (calendario de noticias, señales no ejecutadas que se borraban, VIX/VXN); se indica cuál y cómo conseguirlo."],
        ["Mejora material", "Para contar como mejora: al menos 100 USD o el 10 % del valor de la referencia (neto, segunda mitad, caída máxima), o una semana positiva más."],
        ["Diferencia semanal", "Promedio por semana de (forma − referencia), con su margen remuestreando semanas. Si el margen queda todo bajo cero, empeora con claridad."],
        ["Propuesta de Matriz", "Las formas Candidatas como columnas de la Matriz Recorrido/Escenarios. Tú apruebas, cambias o quitas columnas."],
    ])
