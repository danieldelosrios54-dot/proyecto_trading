"""resumen_escenarios.xlsx: todos los escenarios medidos en una tabla comparable, con su estado y el motivo."""

import numpy as np

from medicion.analisis import Tabla
from simulador.estado_formas import CANDIDATA, DESCARTADA, ESTADOS, NO_MEDIDA, OBSERVACION, consistencia
from simulador.formas import REF

POR_QUE = "Por qué (motivo del estado)"
ENCABEZADOS = [
    "#", "Escenario", "Tipo", "Descripción (qué cambia frente a la referencia)", "Combinaciones positivas", "Combinaciones + 2 mitades",
    "Top 20: ganancia promedio (USD)", "Top 20: 1ª mitad promedio (USD)", "Top 20: 2ª mitad promedio (USD)",
    "Top 20: positivas en ambas mitades", "Top 20: drawdown promedio (USD)", "Top 20: operaciones promedio",
    "Top 20: con vecinas positivas", "Fuera de muestra (USD)", "Diferencia con la referencia (USD)", "Estado", POR_QUE,
]
COLORES = {"Top 20: 2ª mitad promedio (USD)", "Fuera de muestra (USD)", "Diferencia con la referencia (USD)"}
_REFERENCIA = f"Igual que la referencia: orden a ±{REF[0]} ticks, colocación en {REF[1]} ms, deslizamiento de {REF[2]}, cierre a {REF[3]} min, ATM fijo, todas las señales"


def _miles(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _usd(x: float) -> str:
    return f"{x:+,.0f}".replace(",", ".")


def _primera_frase(texto: str) -> str:
    corte = texto.find("Fuera de muestra")
    return (texto[:corte] if corte > 0 else texto).strip()


def _de(parte: int, total: int) -> str:
    return f"{_miles(parte)} de {_miles(total)} ({100 * parte / total:.0f} %)" if total else "0 de 0"


def _nota_variante(nombre: str, colocacion: int | None, es_ref: bool) -> str:
    """Aviso para no contar dos veces el mismo mecanismo al armar la Matriz."""
    if colocacion is not None:
        if es_ref:
            return "Es la misma regla que la referencia («ATM fijo (referencia)»): no es un escenario aparte."
        if colocacion < REF[1]:
            return "Colocación más rápida que la referencia: depende de tu velocidad real; primero hay que medirla en el Log de NinjaTrader."
        return "Variante de parámetros de la referencia (distancia, colocación, cierre o zonas): confirma que el resultado es una meseta; no hace falta como escenario aparte."
    if " en Te " in nombre:
        return f"Variante en una sola Te de «{nombre.split(' en Te ')[0]}»: cuenta como el mismo mecanismo."
    if nombre.startswith("Corte temprano"):
        return "Una de las variantes de parámetros del corte temprano: cuenta como el mismo mecanismo."
    if "2 contratos" in nombre:
        return "Requiere 2 contratos."
    return ""


def _motivo(nombre, ev, estado, argumento, diferencia, ref_top, colocacion=None, es_ref=False) -> str:
    frase = _primera_frase(argumento)
    if ev is None or estado == NO_MEDIDA:
        return frase
    _, texto = consistencia(ev.top, ref_top)
    con_tabla = "ambas_todas" in (ev.top or {})
    if estado == CANDIDATA:
        return " ".join(x for x in (frase, texto if con_tabla else "", _nota_variante(nombre, colocacion, es_ref)) if x)
    if estado == OBSERVACION:
        return " ".join(x for x in (frase, texto if con_tabla else "") if x)
    if estado == DESCARTADA:
        return f"{frase} Fuera de muestra {_usd(ev.fuera.neto)} USD; diferencia con la referencia {_usd(diferencia)} USD."
    return frase


def _fila(nombre, tipo, descripcion, ev, estado, argumento, ref_fuera, ref_top=None, colocacion=None, es_ref=False) -> dict:
    top = ev.top if ev is not None else None
    fuera = None if ev is None else ev.fuera.neto
    diferencia = None if fuera is None else fuera - ref_fuera
    return {
        "Escenario": nombre, "Tipo": tipo, "Descripción (qué cambia frente a la referencia)": descripcion,
        "Combinaciones positivas": None if top is None else _de(top["positivas"], top["combinaciones"]),
        "Combinaciones + 2 mitades": None if top is None or "ambas_todas" not in top else _de(top["ambas_todas"], top["combinaciones"]),
        "Top 20: ganancia promedio (USD)": None if top is None else round(top["ganancia"], 2),
        "Top 20: 1ª mitad promedio (USD)": None if top is None else round(top["mitad1"], 2),
        "Top 20: 2ª mitad promedio (USD)": None if top is None else round(top["mitad2"], 2),
        "Top 20: positivas en ambas mitades": None if top is None else f"{top['ambas']} de {top['n']}",
        "Top 20: drawdown promedio (USD)": None if top is None else round(top["caida"], 2),
        "Top 20: operaciones promedio": None if top is None else round(top["operaciones"]),
        "Top 20: con vecinas positivas": None if top is None or top["vecinas"] is None else f"{top['vecinas']} de {top['n']}",
        "Fuera de muestra (USD)": None if fuera is None else round(fuera, 2),
        "Diferencia con la referencia (USD)": None if diferencia is None else round(diferencia, 2),
        "Estado": estado, POR_QUE: _motivo(nombre, ev, estado, argumento, diferencia, ref_top, colocacion, es_ref),
        "_orden": (ESTADOS.index(estado) if estado in ESTADOS else len(ESTADOS), -(fuera if fuera is not None else -np.inf)),
    }


def tablas(filas, mapa, ref_fuera: float, ref_top: dict | None = None) -> list[Tabla]:
    """`filas`: formas del catálogo; `mapa`: (distancia, colocación, minutos, zonas, evaluación, estado, argumento)."""
    registros = []
    for f in filas:
        descripcion = "; ".join(f"{k}: {v}" for k, v in f.cambio.items()) or _REFERENCIA
        registros.append(_fila(f.forma, "Forma de operar", descripcion, f.ev, f.estado, f.argumento, ref_fuera, ref_top))
    for d, ms, minutos, zonas, ev, estado, argumento in mapa:
        nombre = f"Mapa: ±{d} ticks · {ms} ms · {minutos} min · {zonas}"
        descripcion = f"Orden a ±{d} ticks, colocación en {ms} ms, cierre a {minutos} min, zonas: {zonas}"
        es_ref = (d, ms, minutos, zonas) == (REF[0], REF[1], REF[3], "Todas")
        registros.append(_fila(nombre, "Mapa de reglas", descripcion + (" (igual que la referencia)" if es_ref else ""), ev, estado, argumento, ref_fuera, ref_top, ms, es_ref))
    registros.sort(key=lambda r: r["_orden"])
    filas_tabla = [[i, *[r[k] for k in ENCABEZADOS[1:]]] for i, r in enumerate(registros, 1)]
    cuenta = {e: sum(r["Estado"] == e for r in registros) for e in ESTADOS}
    como_leer = Tabla("Cómo leer el resumen", ["Columna", "Qué significa"], [
        ["Escenario", f"Cada forma de operar medida (tus 16 puntos y las formas nuevas) y cada combinación de reglas del mapa. En total, {len(registros)} escenarios: "
                      + ", ".join(f"{e} {n}" for e, n in cuenta.items() if n) + "."],
        ["Descripción", "Qué cambia frente a la referencia. Lo que no se menciona queda igual que la referencia."],
        ["Combinaciones positivas", "De todas las combinaciones SL/TP (o parámetros) medidas en ese escenario, cuántas ganaron dinero en las 14 semanas."],
        ["Combinaciones + 2 mitades", "De todas las combinaciones, cuántas ganaron en las primeras 7 semanas y también en las últimas 7. Si es mucho menor que Combinaciones positivas, la ganancia depende de una sola época. El motivo compara esa proporción con la de la referencia."],
        ["Top 20", "Las 20 combinaciones con más ganancia mirando las 14 semanas, y sus promedios. Es optimista: se eligen después de ver los resultados."],
        ["Positivas en ambas mitades (top 20)", "Del top 20, cuántas ganaron en las primeras 7 semanas y también en las últimas 7."],
        ["Con vecinas positivas", "Del top 20, cuántas tienen su matriz 3 × 3 de vecinas toda positiva: zonas sólidas, no picos aislados."],
        ["Fuera de muestra", "Se elige la combinación con 13 semanas y se mide en la que no se vio, 14 veces. Es lo más parecido a operar en vivo y el número más honesto para comparar escenarios."],
        ["Diferencia con la referencia", "Fuera de muestra del escenario menos el de la referencia."],
        [CANDIDATA, "Positiva fuera de muestra, en ambas mitades, mejor que la mediana del azar, con una mejora material frente a la referencia y sin depender de una época más que la referencia (la proporción de sus combinaciones positivas que gana en ambas mitades no es menor que la de la referencia). Puede estar en la Matriz principal, sin importar cuántos escenarios tenga."],
        ["En observación", "Positiva fuera de muestra, pero le falta algo (una mitad negativa, no supera al azar o su ganancia depende de una época). Se revisa con semanas nuevas."],
        ["Descartada", "Negativa fuera de muestra, positiva sin dar valor, requiere 2 cuentas o su medición tiene sesgo."],
        ["No Aplica", "No es una decisión, es un costo (deslizamiento): muestra cuánto cambia el resultado."],
        ["No Medida", "Falta un dato para medirla; el motivo dice cuál y cómo conseguirlo."],
        [POR_QUE, "El motivo del estado con sus números. En las candidatas, un aviso si es una variante de otra (misma idea con otros parámetros) para no contarla dos veces al armar la Matriz."],
        ["Celdas vacías", "Las formas que eligen un ATM por grupo, por semana o dentro del día no tienen una tabla de combinaciones: solo tienen Fuera de muestra. Las No Medida no tienen números."],
    ])
    return [Tabla("Resumen escenarios", ENCABEZADOS, filas_tabla), como_leer]
