"""Entregable principal (documento 4): 6 escenarios con cierre por minutos, zonas, semanas y análisis con conclusiones."""

import time
from dataclasses import dataclass
from datetime import date

import numpy as np

import config
from medicion.analisis import Medicion, Tabla
from medicion.entrada import Dia
from simulador import metricas as mt
from simulador.datos import LADO, Conjunto, calendario, conjunto, operaciones_de
from simulador.indicadores import indicadores_serie
from simulador.operaciones import lunes
from simulador.principal import _conteos, _indicadores, _serie_de_dia, _titulo_zona
from simulador.reportes import escribir_libro
from simulador.salidas import fijo_minutos, usd
from simulador.velas_sesion import cargar_velas
from validacion.modelos import Senal

_TICKS = config.SIM_TICKS
REFERENCIA = _TICKS.index(config.ATM_REFERENCIA[0]) * LADO + _TICKS.index(config.ATM_REFERENCIA[1])
_USD = config.USD_POR_TICK
_COMBINACION = ["SL (ticks)", "TP (ticks)", "SL (USD)", "TP (USD)"]
COLUMNAS_20 = [
    "Revision Invalida", "No Ejecutadas", "# Solapamiento", "Hora Entrada", "Ventana Ejecucion", "Prom. Tiempo Abierta",
    "Ganancia Neta", "Esperanza Matematica", "Profit Factor", "Win Rate", "Payoff Ratio", "Drawdown", "Recovery Factor",
    "Combinaciones Vecinas", "Trades +", "Trades -", "Racha Max. (Operaciones -)", "Racha Max. (Dias -)", "$ Peor Dia", "Fecha Peor Dia",
]
CONSISTENCIA = ["Peor mitad", "Semanas positivas"]
COLUMNAS_ZONAS = ["Operaciones", "Ganancia Neta", "Esperanza Matematica", "Win Rate", "Payoff Ratio", "Combinaciones Vecinas", *CONSISTENCIA]
_RENOMBRE = {"# Solapamiento": "Trades (Solapamiento)", "Racha Max. (Operaciones -)": "Racha Max. (Trades -)"}
_CAMBIA = {1: "Escenario principal", 2: "Orden a 7 ticks", 3: "Colocación en 600 ms", 4: "Deslizamiento de entrada 6 ticks", 5: "Cierre a 8 minutos", 6: "Cierre a 5 minutos"}


def matriz_minutos(c: Conjunto, minutos: float) -> tuple[np.ndarray, np.ndarray]:
    """USD y hora de salida de cada operación con cada combinación."""
    valores = np.empty((len(c), LADO * LADO), dtype=np.float32)
    salida = np.empty((len(c), LADO * LADO), dtype=np.int64)
    for k, op in enumerate(c.ops):
        v, i = fijo_minutos(op, minutos)
        valores[k] = usd(v).ravel()
        salida[k] = op.ns[i].ravel()
    return valores, salida


@dataclass
class Resultado:
    """Un escenario o un grupo: columnas por combinación y su resumen semanal."""
    columnas: dict[str, np.ndarray]
    semanal: mt.Semanal
    operaciones: int

    def referencia(self) -> mt.Calificacion:
        return mt._calificar(self.semanal, [REFERENCIA] * self.semanal.neto.shape[0])


def _veinte(c: Conjunto, valores, salida, tomada, filas, mediciones, filtro, ndias, nsem) -> Resultado:
    invalidas, no_ej = _conteos(mediciones, filtro)
    base = mt.columnas(valores[filas], salida[filas], tomada[filas], c.entrada_ns[filas], c.hora_utc_ns[filas], c.dia[filas], ndias, invalidas, no_ej, True)
    s = mt.semanal(valores[filas], tomada[filas], c.semana[filas], nsem)
    columnas = {n: base[_RENOMBRE.get(n, n)] for n in COLUMNAS_20 if n != "Combinaciones Vecinas"}
    columnas["Combinaciones Vecinas"] = mt.combinaciones_vecinas(base["Ganancia Neta"], LADO)
    positivas, con_ops = mt.semanas_positivas(s)
    columnas["Peor mitad"] = mt.peor_mitad(s)
    columnas["Semanas positivas"] = np.array([f"{p} de {con_ops}" for p in positivas], dtype=object)
    return Resultado(columnas, s, len(filas))


def _zona(c: Conjunto, valores, filas, nsem) -> Resultado:
    v = valores[filas].astype(np.float64)
    n = len(filas)
    neto = v.sum(0)
    gana, pierde = v > 0, v < 0
    ganancia_media = np.divide(np.where(gana, v, 0).sum(0), gana.sum(0), out=np.full(neto.shape, np.nan), where=gana.sum(0) > 0)
    perdida_media = np.divide(np.where(pierde, -v, 0).sum(0), pierde.sum(0), out=np.full(neto.shape, np.nan), where=pierde.sum(0) > 0)
    s = mt.semanal(valores[filas], None, c.semana[filas], nsem)
    positivas, con_ops = mt.semanas_positivas(s)
    columnas = {
        "Operaciones": np.full(neto.shape, n), "Ganancia Neta": neto, "Esperanza Matematica": neto / n if n else neto * np.nan,
        "Win Rate": 100 * gana.mean(0), "Payoff Ratio": ganancia_media / perdida_media,
        "Combinaciones Vecinas": mt.combinaciones_vecinas(neto, LADO), "Peor mitad": mt.peor_mitad(s),
        "Semanas positivas": np.array([f"{p} de {con_ops}" for p in positivas], dtype=object),
    }
    return Resultado(columnas, s, n)


def _tabla(titulo: str, nombres: list[str], r: Resultado, fechas: list[date]) -> Tabla:
    valores = {n: r.columnas[n].tolist() for n in nombres}
    filas = []
    for i in range(LADO * LADO):
        sl, tp = _TICKS[i // LADO], _TICKS[i % LADO]
        fila = [sl, tp, sl * _USD, tp * _USD]
        for n in nombres:
            v = valores[n][i]
            fila.append((fechas[v] if v >= 0 else None) if n == "Fecha Peor Dia" else v)
        filas.append(fila)
    return Tabla(titulo, [*_COMBINACION, *nombres], filas)


# ---- pestaña Matriz ------------------------------------------------------------------------------

_DEFINICIONES = [
    ("Revision Invalida", "Señales invalidadas por registro, ticks o precio de la orden (el mismo valor en toda la pestaña)."),
    ("No Ejecutadas", "Señales válidas cuya orden no se colocó o no se activó dentro de la ventana de ejecución."),
    ("# Solapamiento", "Señales ejecutables que se perdieron porque seguía abierta otra operación cuando el precio llegó a su orden."),
    ("Hora Entrada", "Hora promedio de entrada (UTC) de las operaciones tomadas."),
    ("Ventana Ejecucion", "Tiempo promedio entre el cierre de la vela de confirmación y la entrada."),
    ("Prom. Tiempo Abierta", "Tiempo promedio con la posición abierta."),
    ("Ganancia Neta", "Suma en USD de todas las operaciones, con comisión de 1,86 USD y deslizamientos."),
    ("Esperanza Matematica", "Ganancia Neta / número de operaciones: USD por operación."),
    ("Profit Factor", "Ganancias brutas / pérdidas brutas."),
    ("Win Rate", "% de operaciones con neto mayor que 0."),
    ("Payoff Ratio", "Ganancia media / pérdida media."),
    ("Drawdown", "Mayor caída del neto acumulado, por orden de cierre."),
    ("Recovery Factor", "Ganancia Neta / Drawdown."),
    ("Combinaciones Vecinas", "Ganancia Neta más baja de la matriz 3 × 3: la combinación y sus vecinas con SL y TP de −1,5, igual y +1,5 USD (6 en los bordes, 4 en las esquinas). Positiva = toda la zona gana; negativa = pico aislado o borde."),
    ("Peor mitad", "Neto de la mitad de semanas que ganó menos (primeras frente a últimas). Positiva = ganó en las dos partes; negativa = depende de una época."),
    ("Semanas positivas", "Semanas con neto mayor que 0, sobre las semanas con operaciones."),
    ("Trades + / Trades -", "Operaciones con neto positivo / negativo."),
    ("Racha Max. (Operaciones -)", "Máximo de operaciones negativas seguidas."),
    ("Racha Max. (Dias -)", "Máximo de días seguidos con neto negativo (los días sin operaciones no cortan la racha)."),
    ("$ Peor Dia / Fecha Peor Dia", "El día con menor neto y su fecha."),
    ("Operaciones (zonas)", "Señales de la zona ejecutadas; en zonas no hay solapamiento, así que son todas."),
]


def matriz(escenarios: list[int], solapamiento: str, nota_extra: str = "") -> Tabla:
    def col(e: int, campo: str) -> str:
        n, d, ms, desl, minutos = next(x for x in config.ESCENARIOS_PRINCIPAL if x[0] == e)
        return {
            "orden": f'"OHLC" ± {d} ticks', "colocacion": f"00:00:00.{ms:03d}", "desliz": f"Precio orden pendiente ± {desl} ticks",
            "cierre": f"SL y TP; cierre por tiempo: {minutos} minutos desde la entrada",
        }[campo]

    nombres = [("Escenario 1 (principal)" if e == 1 else f"Escenario {e}") for e in escenarios]
    filas = [
        ["Qué cambia", *[_CAMBIA[e] for e in escenarios]],
        ["Revisión", *["Igual"] * len(escenarios)],
        ["Calcular el precio de la orden pendiente", *[col(e, "orden") for e in escenarios]],
        ["Inicio del recorrido tick a tick", *["Igual"] * len(escenarios)],
        ["Colocación de la orden pendiente", *[col(e, "colocacion") for e in escenarios]],
        ["Re-entrada", *[f"Máximo {config.LIMITE_REENTRADA_PRINCIPAL} ticks a favor antes de volver"] * len(escenarios)],
        ["Ventana de ejecución", *["Igual"] * len(escenarios)],
        ["Disparo de la orden pendiente", *["Igual"] * len(escenarios)],
        ["Deslizamiento de entrada", *[col(e, "desliz") for e in escenarios]],
        ["Disparo del cierre", *[col(e, "cierre") for e in escenarios]],
        ["Deslizamiento de salida", *["TP: precio TP (pasando 2 ticks). SL: precio SL − 2. Tiempo: tick de cierre − 2"] * len(escenarios)],
        ["Comisión", *["1,86 USD por operación"] * len(escenarios)],
        ["Solapamiento", *[solapamiento] * len(escenarios)],
        [""],
        ["Combinaciones", "SL y TP de 10 a 140,5 USD cada 1,5 USD (20 a 281 ticks cada 3): 7.744 combinaciones."],
        ["Nivel de evidencia", "El escenario principal está en nivel Candidata: gana en semanas no vistas, pero con la ganancia concentrada en las primeras semanas. Validada exige semanas nuevas registradas sin borrar señales."],
    ]
    if nota_extra:
        filas.append(["Nota", nota_extra])
    filas += [[""], ["COLUMNAS", "Qué registra"]] + [[a, b] for a, b in _DEFINICIONES]
    return Tabla("Matriz", ["Recorrido", *nombres], filas)


# ---- análisis ------------------------------------------------------------------------------------

def comparar(a: mt.Calificacion, b: mt.Calificacion) -> str:
    """'a' o 'b' si gana en el total y en ambas mitades; si no, 'empate'."""
    d = (a.neto - b.neto, a.mitad1 - b.mitad1, a.mitad2 - b.mitad2)
    if all(x > 0 for x in d):
        return "a"
    if all(x < 0 for x in d):
        return "b"
    return "empate"


def _f(x: float) -> str:
    return f"{x:+,.0f}".replace(",", ".")


def _texto_ref(c: mt.Calificacion) -> str:
    return f"{_f(c.neto)} USD (mitades {_f(c.mitad1)} / {_f(c.mitad2)})"


_CLARA = "Clara: gana en el total y en ambas mitades"
_NO_CLARA = "No clara: la ventaja cambia entre mitades"


def conclusiones(res: dict[int, Resultado], fuera: dict[int, mt.Calificacion], zonas: dict[str, Resultado], semanas: dict, candidatas: int, mejor: list[str]) -> list[list]:
    ref = {e: r.referencia() for e, r in res.items()}
    pos = {e: int((r.columnas["Ganancia Neta"] > 0).sum()) for e, r in res.items()}
    filas = []

    def duelo(pregunta, e_otro, nombre_a, nombre_b):
        g = comparar(ref[1], ref[e_otro])
        respuesta = nombre_a if g == "a" else (nombre_b if g == "b" else "Empate")
        dato = f"ATM de referencia: {_texto_ref(ref[1])} con {nombre_a} frente a {_texto_ref(ref[e_otro])} con {nombre_b}. Combinaciones positivas: {pos[1]} frente a {pos[e_otro]}."
        filas.append([pregunta, respuesta, dato, _CLARA if g != "empate" else _NO_CLARA, "Escenarios"])

    duelo("¿Orden pendiente a 3 o a 7 ticks?", 2, "3 ticks", "7 ticks")
    duelo("¿Colocar la orden en 200 o en 600 ms?", 3, "200 ms", "600 ms")
    g = comparar(ref[1], ref[4])
    filas.append([
        "¿Cuánto afecta un deslizamiento de entrada de 6 ticks en vez de 3?",
        "Empeora" if g == "a" else ("Mejora" if g == "b" else "Empate"),
        f"ATM de referencia: {_texto_ref(ref[1])} con 3 ticks frente a {_texto_ref(ref[4])} con 6: diferencia {_f(ref[4].neto - ref[1].neto)} USD. Combinaciones positivas: {pos[1]} frente a {pos[4]}.",
        _CLARA if g != "empate" else _NO_CLARA, "Escenarios",
    ])
    cierres = {1: 9, 5: 8, 6: 5}
    ganadores = [e for e in cierres if all(comparar(ref[e], ref[o]) == "a" for o in cierres if o != e)]
    no_vencidos = [e for e in cierres if not any(comparar(ref[o], ref[e]) == "a" for o in cierres if o != e)]
    respuesta = f"{cierres[ganadores[0]]} minutos" if ganadores else "Empate entre " + ", ".join(f"{cierres[e]}" for e in no_vencidos) + " minutos"
    filas.append([
        "¿Cerrar por tiempo a 9, 8 o 5 minutos?", respuesta,
        " · ".join(f"{cierres[e]} min: {_texto_ref(ref[e])}" for e in cierres),
        _CLARA if ganadores else _NO_CLARA, "Escenarios",
    ])

    restan = [(z, r) for z, r in zonas.items() if r.referencia().neto < 0]
    texto = "; ".join(f"{z} {_f(r.referencia().neto)} USD en {r.operaciones} operaciones{' (poca muestra)' if r.operaciones < config.MUESTRA_MINIMA else ''}" for z, r in restan)
    filas.append([
        "¿Alguna Zona Reacción resta con el ATM de referencia?", "Sí: " + ", ".join(z for z, _ in restan) if restan else "No",
        (texto + ". " if restan else "") + "Medido sin solapamiento, cada zona sola.",
        "Débil: pocas señales por zona; confirmar con semanas nuevas", "Zonas",
    ])

    perdedoras = [s for s, d in semanas.items() if d["neto"] < 0]
    sin_ganadora = [s for s, d in semanas.items() if d["positivas"] == 0]
    atr_mal = np.nanmean([semanas[s]["atr5"] for s in perdedoras]) if perdedoras else np.nan
    atr_bien = np.nanmean([d["atr5"] for s, d in semanas.items() if d["neto"] >= 0])
    filas.append([
        "¿Qué semanas fallaron y cómo estaba el mercado?", f"{len(perdedoras)} de {len(semanas)} semanas en pérdida",
        f"Perdieron: {', '.join(perdedoras)}. Sin ninguna combinación ganadora: {', '.join(sin_ganadora) or 'ninguna'}. ATR(5) promedio: {atr_mal:.1f} puntos en las semanas perdedoras frente a {atr_bien:.1f} en las ganadoras.",
        "Descriptivo: muestra qué pasó, no anticipa la semana siguiente", "Semanas",
    ])
    filas.append([
        "¿Qué combinaciones son sólidas y consistentes?", f"{candidatas} combinaciones",
        "Cumplen a la vez Ganancia Neta > 0, Combinaciones Vecinas > 0 y Peor mitad > 0 en el Escenario 1. Las primeras: " + "; ".join(mejor[:3]) + ".",
        "Elegidas con los mismos datos: confirmar con semanas nuevas", "Combinaciones candidatas",
    ])
    f1 = fuera[1]
    candidata = f1.neto > 0 and f1.mitad1 > 0 and f1.mitad2 > 0
    filas.append([
        "¿El escenario principal gana en semanas no vistas?", "Sí" if f1.neto > 0 else "No",
        f"Eligiendo la mejor zona de SL/TP con 13 semanas y midiendo en la que falta (14 veces): {_texto_ref(f1)}, Profit Factor {f1.pf:.2f}, {f1.semanas_positivas} semanas positivas de 14.",
        "Candidata" if candidata else "No candidata", "Escenarios",
    ])
    return filas


def _tablas_analisis(res, fuera, zonas, semanas_info, ejecutadas, no_ejecutadas) -> tuple[list[Tabla], dict]:
    ref = {e: r.referencia() for e, r in res.items()}
    filas_esc = []
    for e, r in res.items():
        c = ref[e]
        filas_esc.append([
            e, _CAMBIA[e], ejecutadas[e], no_ejecutadas[e], int((r.columnas["Ganancia Neta"] > 0).sum()),
            round(c.neto, 2), round(c.pf, 2), c.operaciones, round(min(c.mitad1, c.mitad2), 2), f"{c.semanas_positivas} de {r.semanal.neto.shape[0]}",
            round(fuera[e].neto, 2), round(fuera[e].pf, 2), round(c.neto - ref[1].neto, 2),
        ])
    escenarios = Tabla("Escenarios", [
        "Escenario", "Qué cambia", "Ejecutadas", "No ejecutadas", "Combinaciones positivas", "ATM ref.: neto (USD)", "ATM ref.: PF",
        "ATM ref.: operaciones", "ATM ref.: peor mitad (USD)", "ATM ref.: semanas positivas", "Fuera de muestra: neto (USD)",
        "Fuera de muestra: PF", "Diferencia con E1 (USD)",
    ], filas_esc)

    r1 = res[1].columnas
    neto, vec, peor = r1["Ganancia Neta"], r1["Combinaciones Vecinas"], r1["Peor mitad"]
    validas = np.flatnonzero((neto > 0) & (vec > 0) & (peor > 0))
    orden = validas[np.argsort(-neto[validas])][:config.CANDIDATAS_MAX]
    filas_cand, mejor = [], []
    for i in orden:
        sl, tp = _TICKS[i // LADO], _TICKS[i % LADO]
        filas_cand.append([sl, tp, sl * _USD, tp * _USD, round(neto[i], 2), round(r1["Profit Factor"][i], 2), round(r1["Win Rate"][i], 1), round(vec[i], 2), round(peor[i], 2), r1["Semanas positivas"][i], round(r1["Drawdown"][i], 2), "Sí" if i == REFERENCIA else ""])
        mejor.append(f"SL {sl * _USD:g} / TP {tp * _USD:g} USD ({_f(neto[i])})")
    candidatas = Tabla("Combinaciones candidatas", [*_COMBINACION, "Ganancia Neta", "Profit Factor", "Win Rate", "Combinaciones Vecinas", "Peor mitad", "Semanas positivas", "Drawdown", "¿Es el ATM de referencia?"], filas_cand)

    filas_z = []
    for z, r in zonas.items():
        c = r.referencia()
        cols = r.columnas
        solida = np.flatnonzero((cols["Ganancia Neta"] > 0) & (cols["Combinaciones Vecinas"] > 0) & (cols["Peor mitad"] > 0))
        mejor_z = int(solida[np.argmax(cols["Ganancia Neta"][solida])]) if solida.size else None
        filas_z.append([
            z, r.operaciones, "Poca muestra" if r.operaciones < config.MUESTRA_MINIMA else "", round(c.neto, 2),
            round(c.neto / r.operaciones, 2) if r.operaciones else None, round(min(c.mitad1, c.mitad2), 2), cols["Semanas positivas"][REFERENCIA],
            None if mejor_z is None else _TICKS[mejor_z // LADO] * _USD, None if mejor_z is None else _TICKS[mejor_z % LADO] * _USD,
            None if mejor_z is None else round(cols["Ganancia Neta"][mejor_z], 2), "Aporta" if c.neto > 0 else "Resta",
        ])
    zonas_t = Tabla("Zonas", [
        "Zona Reacción", "Operaciones", "Muestra", "ATM ref.: neto (USD)", "ATM ref.: USD por operación", "ATM ref.: peor mitad (USD)",
        "ATM ref.: semanas positivas", "Mejor combinación sólida: SL (USD)", "Mejor combinación sólida: TP (USD)", "Mejor combinación sólida: neto (USD)", "¿Aporta o resta?",
    ], filas_z)

    filas_s = [[s, d["operaciones"], round(d["neto"], 2), d["positivas"], round(100 * d["positivas"] / (LADO * LADO), 1), d["atr5"], d["range"], d["atr_ny"], "Ganó" if d["neto"] >= 0 else "Perdió"] for s, d in semanas_info.items()]
    semanas_t = Tabla("Semanas", ["Semana (lunes)", "ATM ref.: operaciones", "ATM ref.: neto (USD)", "Combinaciones positivas", "% combinaciones positivas", "ATR(5) promedio (puntos)", "Range promedio (puntos)", "ATR NY promedio (puntos)", "Resultado"], filas_s)
    colores = {"Escenarios": {"Diferencia con E1 (USD)", "ATM ref.: neto (USD)", "Fuera de muestra: neto (USD)"}, "Zonas": {"ATM ref.: neto (USD)", "ATM ref.: peor mitad (USD)"}, "Semanas": {"ATM ref.: neto (USD)"}, "Combinaciones candidatas": set()}
    return [escenarios, candidatas, zonas_t, semanas_t], {"colores": colores, "candidatas": len(validas), "mejor": mejor}


def _como_leer(conclus: list[list], tablas: list[Tabla]) -> Tabla:
    esc = tablas[0].filas[0] if tablas[0].filas else None
    filas = [
        ["Conclusiones", "Responde cada pregunta en una frase con los números que la respaldan. Clara = la ventaja se repite en el total y en ambas mitades de las semanas; si no, Empate.", f"Primera pregunta: {conclus[0][0]} → {conclus[0][1]}." if conclus else ""],
        ["Escenarios", f"Una fila por escenario. El ATM de referencia (SL {config.ATM_REFERENCIA[0] * _USD:g} / TP {config.ATM_REFERENCIA[1] * _USD:g} USD) permite comparar escenarios con el mismo SL/TP. Verde = mejor que el E1; rojo = peor.", f"Escenario 1: {esc[5]:,.0f} USD con el ATM de referencia." if esc else ""],
        ["Combinaciones candidatas", "Combinaciones del Escenario 1 que ganan, cuya zona 3 × 3 también gana y que ganaron en las dos mitades. Ordenadas por Ganancia Neta.", ""],
        ["Zonas", "Cada zona medida sola (sin solapamiento). Resta = con el ATM de referencia perdió dinero. Poca muestra = menos de 30 señales.", ""],
        ["Semanas", "Cada semana con el ATM de referencia, cuántas combinaciones ganaron y cómo estaba la volatilidad (ATR y Range en puntos, como en NinjaTrader).", ""],
    ]
    return Tabla("Cómo leer", ["Pestaña", "Cómo leerla", "Ejemplo con tus datos"], filas)


def ejecutar_principal(senales: list[Senal], mediciones: dict[int, list[Medicion]], minutos: dict[int, int], dias: dict[str, Dia], atr_ny: dict, avisar=print) -> dict:
    inicio = time.time()
    cal = calendario(mediciones[1], dias)
    nsem, ndias = len(cal.semanas), len(cal.dias)
    fechas = [date(int(d[:4]), int(d[4:6]), int(d[6:])) for d in cal.dias]
    conjuntos = {e: conjunto(operaciones_de(m, dias), dias, cal) for e, m in mediciones.items()}

    res, fuera, matrices = {}, {}, {}
    for e, c in conjuntos.items():
        avisar(f"  Escenario {e} (cierre a {minutos[e]} minutos)...")
        valores, salida = matriz_minutos(c, minutos[e])
        tomada = mt.tomar_sin_solape(c.entrada_ns, salida)
        res[e] = _veinte(c, valores, salida, tomada, np.arange(len(c)), mediciones[e], lambda x: True, ndias, nsem)
        fuera[e] = mt.fuera_de_muestra(res[e].semanal, LADO)
        if e == 1:
            matrices[1] = (valores, salida, tomada)
        else:
            del valores, salida, tomada

    avisar("Escribiendo combinaciones_principal...")
    escenarios = list(res)
    hojas = [matriz(escenarios, "Sí")]
    for e in escenarios:
        hojas.append(_tabla("Escenario 1 (Principal)" if e == 1 else f"Escenario {e}", COLUMNAS_20[:14] + CONSISTENCIA + COLUMNAS_20[14:], res[e], fechas))
    escribir_libro(config.REPORTE_PRINCIPAL, hojas)

    c1 = conjuntos[1]
    valores, salida, tomada = matrices[1]
    avisar("Zonas...")
    zonas, hojas = {}, [matriz([1], "No: cada zona se mide sola")]
    for z, nombre in enumerate(cal.zonas):
        filas = np.flatnonzero(c1.zona == z)
        zonas[nombre] = _zona(c1, valores, filas, nsem)
        hojas.append(_tabla(_titulo_zona(nombre, len(filas)), COLUMNAS_ZONAS, zonas[nombre], fechas))
    escribir_libro(config.REPORTE_PRINCIPAL_ZONAS, hojas)

    avisar("Semanas e indicadores...")
    velas = cargar_velas(config.CARPETA_DATA_TICKS, config.CARPETA_VELAS_SESION, avisar)
    series = {te: indicadores_serie(velas, te) for te in config.VALORES_TE}
    ind = _indicadores(c1, velas, series, _serie_de_dia(), atr_ny, dias)
    hojas, semanas_info = [matriz([1], "Sí", "En este archivo no van Peor mitad ni Semanas positivas: cada pestaña ya es una sola semana.")], {}
    for w, lun in enumerate(cal.semanas):
        filas = np.flatnonzero(c1.semana == w)
        r = _veinte(c1, valores, salida, tomada, filas, mediciones[1], lambda x, lun=lun: x.senal.fecha is not None and lunes(x.senal.fecha) == lun, ndias, nsem)
        hojas.append(_tabla(f"Semana {lun}", COLUMNAS_20, r, fechas))
        ref_w = int(tomada[filas, REFERENCIA].sum())
        semanas_info[str(lun)] = {
            "operaciones": ref_w, "neto": float(r.columnas["Ganancia Neta"][REFERENCIA]),
            "positivas": int((r.columnas["Ganancia Neta"] > 0).sum()),
            "atr5": round(float(np.nanmean(ind["ATR (5)"][filas])), 2), "range": round(float(np.nanmean(ind["Range"][filas])), 2),
            "atr_ny": round(float(np.nanmean(ind["ATR NY desde la apertura (referencia)"][filas])), 2),
        }
    escribir_libro(config.REPORTE_PRINCIPAL_SEMANA, hojas)

    avisar("Análisis...")
    ejecutadas = {e: len(c) for e, c in conjuntos.items()}
    no_ej = {e: sum(1 for m in mediciones[e] if m.revision == config.REVISION_VALIDA and m.ejecucion != config.EJECUTADA) for e in mediciones}
    tablas, extra = _tablas_analisis(res, fuera, zonas, semanas_info, ejecutadas, no_ej)
    conclus = conclusiones(res, fuera, zonas, semanas_info, extra["candidatas"], extra["mejor"])
    hoja_conc = Tabla("Conclusiones", ["Pregunta", "Respuesta", "Dato que la respalda", "Nivel de evidencia", "Ver detalle en"], conclus)
    escribir_libro(config.REPORTE_ANALISIS_PRINCIPAL, [hoja_conc, *tablas, _como_leer(conclus, tablas)], extra["colores"])

    return {
        "Segundos": round(time.time() - inicio),
        "Ejecutadas por escenario": ejecutadas,
        "ATM de referencia E1 (USD)": round(res[1].referencia().neto, 2),
        "Fuera de muestra E1 (USD)": round(fuera[1].neto, 2),
        "Combinaciones candidatas": extra["candidatas"],
    }
