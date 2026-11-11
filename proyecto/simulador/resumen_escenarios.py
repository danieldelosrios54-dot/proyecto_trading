"""resumen_escenarios.xlsx: todos los escenarios medidos en una tabla comparable, con su estado y el motivo,
agrupados por idea (Grupos) y con la zona de combinaciones utilizables de cada grupo."""

import re
from collections import defaultdict

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from medicion.analisis import Tabla
from simulador.datos import combinacion
from simulador.estado_formas import CANDIDATA, DESCARTADA, ESTADOS, NO_MEDIDA, OBSERVACION, consistencia, proporcion_ambas
from simulador.formas import REF, _USD

POR_QUE = "Por qué (motivo del estado)"
ENCABEZADOS = [
    "#", "Escenario", "Grupo", "Tipo", "Descripción (qué cambia frente a la referencia)", "Combinaciones positivas", "Combinaciones + 2 mitades",
    "Top 20: ganancia promedio (USD)", "Top 20: 1ª mitad promedio (USD)", "Top 20: 2ª mitad promedio (USD)",
    "Top 20: positivas en ambas mitades", "Top 20: drawdown promedio (USD)", "Top 20: operaciones promedio",
    "Top 20: con vecinas positivas", "Fuera de muestra (USD)", "Diferencia con la referencia (USD)", "Estado", POR_QUE,
]
COLORES = {"Top 20: 2ª mitad promedio (USD)", "Fuera de muestra (USD)", "Diferencia con la referencia (USD)"}
GRUPO_REFERENCIA = "Referencia y su meseta"
GRUPO_SIN_TREND_V = "Sin Trend ≥ 2do Pivot ni V y su meseta"
_REGLAS_GRUPO = [
    (r"^(Dejar de operar .+?) en Te \d", None),
    (r"^Corte temprano", "Corte temprano"),
    (r"^Cierre condicionado", "Cierre condicionado"),
    (r"^Breakeven", "Breakeven"),
    (r"^Stop límite", "Stop límite"),
    (r"^Varias posiciones en la misma dirección", "Varias posiciones en la misma dirección"),
    (r"^Separación mínima", "Separación mínima entre entradas"),
    (r"^No operar si la orden está a más de \d+ ticks", "No operar órdenes lejanas del cierre de la vela"),
    (r"^Pausa si las últimas \d+ operaciones", "Pausa por resultado reciente"),
    (r"^Un ATM por Zona Reacción", "Un ATM por Zona Reacción"),
    (r"^Prioridad a .+ cuando entran a la vez", "Prioridad entre señales simultáneas"),
    (r"^Ventana:", "Acortar la ventana de ejecución"),
    (r"^Deslizamiento de entrada", "Deslizamiento de entrada"),
]
GRUPOS_ENCABEZADOS = [
    "Grupo", "Escenarios", "Candidatas", "En observación", "Descartadas", "No Aplica / No Medida",
    "Fuera de muestra mínimo (USD)", "Fuera de muestra máximo (USD)", "% de positivas que ganan en ambas mitades",
    "Mejor escenario", "Combinaciones utilizables", "Combinación de referencia del grupo", "Elecciones fuera de muestra dentro de la zona",
]
UTILIZABLES_ENCABEZADOS = [
    "Grupo", "SL (USD)", "TP (USD)", "Parámetro", "Escenarios candidatos", "Neto mínimo (USD)", "Neto promedio (USD)",
    "Neto máximo (USD)", "Peor mitad mínima (USD)", "Vecinas utilizables",
]
_REFERENCIA = f"Igual que la referencia: orden a ±{REF[0]} ticks, colocación en {REF[1]} ms, deslizamiento de {REF[2]}, cierre a {REF[3]} min, ATM fijo, todas las señales"


def _miles(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _usd(x: float) -> str:
    return f"{x:+,.0f}".replace(",", ".")


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _primera_frase(texto: str) -> str:
    corte = texto.find("Fuera de muestra")
    return (texto[:corte] if corte > 0 else texto).strip()


def _de(parte: int, total: int) -> str:
    return f"{_miles(parte)} de {_miles(total)} ({100 * parte / total:.0f} %)" if total else "0 de 0"


# ---- grupos ------------------------------------------------------------------------------------------

def grupo(nombre: str, tipo: str) -> str:
    """Idea a la que pertenece un escenario: sus variantes de parámetros van juntas."""
    if tipo == "Mapa de reglas":
        zonas = nombre.rsplit(" · ", 1)[-1]
        return GRUPO_REFERENCIA if zonas == "Todas" else (GRUPO_SIN_TREND_V if zonas == "Sin Trend ≥ 2do Pivot ni V" else f"Mapa: {zonas}")
    if nombre == "ATM fijo (referencia)":
        return GRUPO_REFERENCIA
    if nombre == "Dejar de operar Trend ≥ 2do Pivot y V":
        return GRUPO_SIN_TREND_V
    for patron, nombre_grupo in _REGLAS_GRUPO:
        m = re.match(patron, nombre)
        if m:
            return nombre_grupo or m.group(1)
    return nombre


def _etiqueta(pc: dict, i: int) -> tuple:
    """(SL USD, TP USD, parámetro) de la combinación i."""
    if pc["lado"]:
        sl, tp = combinacion(int(i))
        return sl * _USD, tp * _USD, None
    return None, None, pc["nombres"][i] if pc["nombres"] else str(i)


def _vecinas(ok: np.ndarray, lado: int) -> tuple[np.ndarray, np.ndarray]:
    """(vecinas utilizables, vecinas que existen) de cada combinación en la cuadrícula SL × TP."""
    rejilla = np.pad(ok.reshape(lado, lado).astype(float), 1, constant_values=np.nan)
    ventanas = sliding_window_view(rejilla, (3, 3))
    existen = (~np.isnan(ventanas)).sum((-2, -1)) - 1
    utiles = np.nansum(ventanas, (-2, -1)) - ok.reshape(lado, lado)
    return utiles.ravel().astype(int), existen.ravel().astype(int)


def _sin_zona(texto: str, elecciones=None) -> dict:
    return {"texto": texto, "referencia": None, "elecciones": elecciones, "filas": []}


def utilizables(evaluaciones: list) -> dict:
    """Combinaciones que ganan en el total y en ambas mitades en todos los escenarios candidatos de un grupo.

    `evaluaciones`: las de los escenarios Candidata del grupo. Devuelve "texto" (resumen), "referencia" (la de mayor
    neto mínimo), "elecciones" (elecciones fuera de muestra dentro de la zona) y "filas" (detalle por combinación).
    """
    if not evaluaciones:
        return _sin_zona("No aplica: ningún escenario del grupo es candidato.")
    pcs = [ev.top["por_combinacion"] for ev in evaluaciones if ev is not None and ev.top and "por_combinacion" in ev.top]
    if not pcs:
        return _sin_zona("No aplica: sus candidatas eligen el ATM por grupo, sin una tabla de combinaciones.")
    if len({len(pc["total"]) for pc in pcs}) > 1:
        return _sin_zona("No aplica: sus candidatas usan tablas de combinaciones distintas.")
    total = np.vstack([pc["total"] for pc in pcs]).astype(float)
    primera = np.vstack([pc["primera"] for pc in pcs]).astype(float)
    segunda = np.vstack([pc["segunda"] for pc in pcs]).astype(float)
    ok = ((total > 0) & (primera > 0) & (segunda > 0)).all(0)
    n, k = int(ok.sum()), len(pcs)
    elegidas = [e for pc in pcs for e in pc["elegidas"]]
    dentro = sum(bool(ok[e]) for e in elegidas)
    elecciones = f"{dentro} de {len(elegidas)} ({100 * dentro / len(elegidas):.0f} %)" if elegidas else None
    escenarios = f"en las {k} candidatas del grupo" if k > 1 else "en su candidata"
    if n == 0:
        return _sin_zona(f"Ninguna: no hay combinación que gane en el total y en ambas mitades {escenarios}.", elecciones)
    pc0 = pcs[0]
    minimo, promedio, maximo = total.min(0), total.mean(0), total.max(0)
    peor_mitad = np.minimum(primera, segunda).min(0)
    vec, existen = _vecinas(ok, pc0["lado"]) if pc0["lado"] else (None, None)
    indices = np.flatnonzero(ok)
    indices = indices[np.argsort(-minimo[indices], kind="stable")]
    filas = []
    for i in indices:
        sl, tp, parametro = _etiqueta(pc0, i)
        filas.append([sl, tp, parametro, k, round(float(minimo[i]), 2), round(float(promedio[i]), 2), round(float(maximo[i]), 2),
                      round(float(peor_mitad[i]), 2), None if vec is None else f"{vec[i]} de {existen[i]}"])
    mejor = int(indices[0])
    sl, tp, parametro = _etiqueta(pc0, mejor)
    nombre_mejor = f"SL {_num(sl)} / TP {_num(tp)} USD" if parametro is None else parametro
    referencia = f"{nombre_mejor}; neto mínimo entre escenarios {_usd(minimo[mejor])} USD" + (
        f"; {vec[mejor]} de {existen[mejor]} vecinas utilizables" if vec is not None else "")
    if pc0["lado"]:
        sls = [combinacion(int(i))[0] * _USD for i in indices]
        tps = [combinacion(int(i))[1] * _USD for i in indices]
        texto = f"{_miles(n)} de {_miles(len(ok))} combinaciones {escenarios}: SL entre {_num(min(sls))} y {_num(max(sls))} USD, TP entre {_num(min(tps))} y {_num(max(tps))} USD."
    else:
        texto = f"{_miles(n)} de {_miles(len(ok))} combinaciones {escenarios}."
    return {"texto": texto, "referencia": referencia, "elecciones": elecciones, "filas": filas}


def tabla_grupos(registros: list[dict]) -> tuple[list[list], list[list]]:
    """Filas de las pestañas "Grupos" y "Combinaciones utilizables"."""
    por_grupo = defaultdict(list)
    for reg in registros:
        por_grupo[reg["Grupo"]].append(reg)
    filas, orden, detalle = [], [], {}
    for nombre, regs in por_grupo.items():
        estados = [reg["Estado"] for reg in regs]
        fueras = [reg["Fuera de muestra (USD)"] for reg in regs if reg["Fuera de muestra (USD)"] is not None]
        props = [p for p in (proporcion_ambas(reg["_ev"].top if reg["_ev"] is not None else None) for reg in regs) if p is not None]
        candidatas = [reg for reg in regs if reg["Estado"] == CANDIDATA]
        con_fuera = [reg for reg in (candidatas or regs) if reg["Fuera de muestra (USD)"] is not None]
        mejor = max(con_fuera, key=lambda reg: reg["Fuera de muestra (USD)"])["Escenario"] if con_fuera else None
        zona = utilizables([reg["_ev"] for reg in candidatas])
        n_cand, n_obs, n_desc = estados.count(CANDIDATA), estados.count(OBSERVACION), estados.count(DESCARTADA)
        filas.append([
            nombre, len(regs), n_cand, n_obs, n_desc, len(regs) - n_cand - n_obs - n_desc,
            min(fueras) if fueras else None, max(fueras) if fueras else None,
            (f"{100 * props[0]:.0f} %" if len(props) == 1 else f"{100 * min(props):.0f} % a {100 * max(props):.0f} %") if props else None,
            mejor, zona["texto"], zona["referencia"], zona["elecciones"],
        ])
        orden.append((0 if n_cand else (1 if n_obs else 2), -(max(fueras) if fueras else -np.inf)))
        detalle[nombre] = [[nombre, *f] for f in zona["filas"]]
    filas = [f for _, f in sorted(zip(orden, filas), key=lambda x: x[0])]
    return filas, [d for f in filas for d in detalle[f[0]]]


# ---- tabla principal -------------------------------------------------------------------------------------

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
        "Escenario": nombre, "Grupo": grupo(nombre, tipo), "Tipo": tipo, "_ev": ev,
        "Descripción (qué cambia frente a la referencia)": descripcion,
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
    filas_grupos, filas_utilizables = tabla_grupos(registros)
    ideas_candidatas = sum(1 for f in filas_grupos if f[2])
    cuenta = {e: sum(r["Estado"] == e for r in registros) for e in ESTADOS}
    como_leer = Tabla("Cómo leer el resumen", ["Columna", "Qué significa"], [
        ["Escenario", f"Cada forma de operar medida (tus 16 puntos y las formas nuevas) y cada combinación de reglas del mapa. En total, {len(registros)} escenarios: "
                      + ", ".join(f"{e} {n}" for e, n in cuenta.items() if n) + "."],
        ["Grupo", f"La idea a la que pertenece el escenario: sus variantes de parámetros (distancia, colocación, cierre, minutos, ticks, Te) van juntas. "
                  f"Hay {len(filas_grupos)} grupos; {ideas_candidatas} tienen al menos una candidata. Al armar la Matriz principal se cuentan grupos, no filas."],
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
        ["Pestaña Grupos", "Una fila por idea: cuántos escenarios tiene en cada estado, su rango de Fuera de muestra, su mejor escenario y su zona de combinaciones utilizables."],
        ["Combinaciones utilizables", "Por grupo: las combinaciones SL/TP (o de parámetros) que ganan en el total de las 14 semanas y en ambas mitades en TODOS los escenarios candidatos del grupo. Es la zona de ATM que funciona venga la variante que venga. Se eligen mirando las 14 semanas, así que son optimistas, como el top 20."],
        ["Combinación de referencia del grupo", "De las utilizables, la de mayor neto mínimo entre los escenarios del grupo (la que mejor aguanta en su peor escenario), con cuántas de sus vecinas en la cuadrícula SL × TP también son utilizables: si son todas, está en el centro de la zona y no en un borde."],
        ["Elecciones fuera de muestra dentro de la zona", "Prueba de honestidad: de las combinaciones que el método eligió sin ver cada semana (14 por escenario candidato), cuántas caen dentro de la zona utilizable. Si casi todas caen dentro, la zona es la que se elige también sin mirar el resultado."],
        ["Pestaña Combinaciones utilizables", "El detalle de cada zona: una fila por combinación utilizable, con su neto mínimo, promedio y máximo entre los escenarios candidatos del grupo, su peor mitad y sus vecinas utilizables. Filtra por Grupo para ver la forma de la zona."],
        ["Límite", "Una meseta o una zona es un argumento de robustez a los parámetros con los mismos datos (703 señales, 14 semanas). No prueba que la idea funcione en semanas nuevas."],
        ["Celdas vacías", "Las formas que eligen un ATM por grupo, por semana o dentro del día no tienen una tabla de combinaciones: solo tienen Fuera de muestra. Las No Medida no tienen números."],
    ])
    return [Tabla("Resumen escenarios", ENCABEZADOS, filas_tabla), Tabla("Grupos", GRUPOS_ENCABEZADOS, filas_grupos),
            Tabla("Combinaciones utilizables", UTILIZABLES_ENCABEZADOS, filas_utilizables), como_leer]
