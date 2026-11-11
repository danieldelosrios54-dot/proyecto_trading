"""Documento 5: medir todas las formas de ejecutar las señales y proponer los escenarios de la nueva Matriz.

Cada forma cambia solo lo que define; el resto queda como el escenario de referencia (orden a ±3 ticks,
colocación en 200 ms, deslizamiento de 3, cierre a 9 minutos, re-entrada de 60 ticks, SL al precio − 2).
Todas se miden igual: dentro, fuera de muestra (13 semanas y 1), mitades, semanas positivas, caída máxima,
frente al azar y frente a la referencia.
"""

import csv
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

import config
from medicion.analisis import Medicion, Tabla
from medicion.entrada import Dia, Escenario, precio_base_y_cierre, signo_de
from simulador import metricas as mt
from simulador import salidas
from simulador import salidas_formas as sf
from simulador.datos import LADO, Calendario, Conjunto, al_azar, calendario, combinacion, conjunto
from simulador.estado_formas import CANDIDATA, DESCARTADA, NO_APLICA, NO_MEDIDA, OBSERVACION, Evaluacion, decidir
from simulador.operaciones import Minutos, Operacion, crear_operacion
from simulador.posiciones import orden_con_prioridad, tomar
from simulador.principal import _conteos, _indicadores, _serie_de_dia
from simulador.principal_escenarios import _RENOMBRE, COLUMNAS_20
from simulador.indicadores import indicadores_serie
from simulador.reportes import escribir_libro
from simulador.velas_sesion import cargar_velas
from validacion.modelos import Senal, clave_fecha, ns_del_dia

_NS_MIN = 60_000_000_000
_USD = config.USD_POR_TICK
REF = config.ESCENARIO_FORMAS  # (distancia, colocación ms, deslizamiento, minutos)
_NOMBRE_MES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
               9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}

# Datos del escenario que se está midiendo, para las columnas del entregable de cada combinación.
# `base()` los fija cada vez que arma las operaciones de un escenario (las evaluaciones van justo después).
CONTEXTO: dict = {"meses": None, "nombres_meses": [], "n_dias": 0, "fechas": [], "conteos": (0, 0)}


def meses_de_semanas(semanas: list[date]) -> tuple[np.ndarray, list[str]]:
    """Índice de mes de cada semana y nombres de los meses. Cada semana va al mes de su miércoles
    (29 jun – 31 jul = julio, 3 – 28 ago = agosto, 31 ago – 2 oct = septiembre)."""
    claves = [(d + timedelta(days=2)).year * 12 + (d + timedelta(days=2)).month for d in semanas]
    orden = sorted(set(claves))
    return np.array([orden.index(k) for k in claves], dtype=int), [_NOMBRE_MES[(k - 1) % 12 + 1] for k in orden]


# ---- datos de cada operación ---------------------------------------------------------------------

@dataclass
class Base:
    """Operaciones de un escenario y sus etiquetas conocidas antes de entrar."""
    c: Conjunto
    meds: dict[int, Medicion]  # por fila
    signo: np.ndarray
    etiquetas: dict[str, np.ndarray] = field(default_factory=dict)


def operaciones(mediciones: list[Medicion], dias: dict[str, Dia], ajuste: Callable[[Medicion], int] | None = None, ancla_orden: bool = False) -> list[Operacion]:
    """Operaciones ejecutadas. `ajuste` cambia el deslizamiento; `ancla_orden` mide SL/TP desde el precio de la orden."""
    ops = []
    for m in mediciones:
        if m.ejecucion != config.EJECUTADA:
            continue
        s = m.senal
        signo = signo_de(s)
        precio = m.precio_op if ancla_orden else m.precio_entrada + (signo * ajuste(m) if ajuste else 0)
        ops.append(crear_operacion(s.fila, clave_fecha(s.fecha), s.fecha, str(s.zona), str(s.tipo), s.te, dias[clave_fecha(s.fecha)], m.indice, precio, signo, ns_del_dia(s.fecha, s.hora_utc_s), velas=22))
    return ops


def base(mediciones: list[Medicion], dias: dict[str, Dia], cal: Calendario, **kw) -> Base:
    c = conjunto(operaciones(mediciones, dias, **kw), dias, cal)
    meds = {m.senal.fila: m for m in mediciones}
    signo = np.array([1 if o.tipo == "Buy" else -1 for o in c.ops])
    meses, nombres_meses = meses_de_semanas(cal.semanas)
    CONTEXTO.update(meses=meses, nombres_meses=nombres_meses, n_dias=len(cal.dias),
                    fechas=[date(int(d[:4]), int(d[4:6]), int(d[6:])) for d in cal.dias], conteos=_conteos(mediciones, lambda m: True))
    return Base(c, meds, signo)


def matriz(c: Conjunto, funcion: Callable[[Operacion], tuple[np.ndarray, np.ndarray]], columnas: int = LADO * LADO) -> tuple[np.ndarray, np.ndarray]:
    valores = np.empty((len(c), columnas), dtype=np.float32)
    salida = np.empty((len(c), columnas), dtype=np.int64)
    for k, op in enumerate(c.ops):
        v, i = funcion(op)
        valores[k] = salidas.usd(np.asarray(v, dtype=float)).ravel()
        salida[k] = op.ns[np.asarray(i)].ravel()
    return valores, salida


def fijo(minutos: float = REF[3]):
    return lambda op: salidas.fijo(op, Minutos(minutos))


# ---- evaluación común ------------------------------------------------------------------------------

def _caida(valores: np.ndarray, orden: np.ndarray) -> float:
    acumulado = np.cumsum(valores[np.argsort(orden, kind="stable")])
    return float((np.maximum.accumulate(np.maximum(acumulado, 0)) - acumulado).max()) if len(acumulado) else 0.0


def evaluar(c: Conjunto, valores, salida, tomada, nsem: int, lado: int | None = LADO, nombres: list[str] | None = None, peso: np.ndarray | None = None) -> Evaluacion:
    """Elige la combinación (o parámetro) con 13 semanas y mide en la que falta, 14 veces."""
    v = valores if peso is None else valores * peso[:, None]
    s = mt.semanal(v, tomada, c.semana, nsem)
    dentro, fuera = mt.dentro_de_muestra(s, lado), mt.fuera_de_muestra(s, lado)
    elegidas = np.array(fuera.elegidas)[c.semana]
    filas = np.arange(len(c))
    toma = tomada[filas, elegidas]
    caida = _caida(v[filas, elegidas][toma].astype(float), salida[filas, elegidas][toma])
    mas = Counter(fuera.elegidas).most_common(1)[0][0]
    if nombres is not None:
        texto, vecinas = nombres[mas], None
    elif lado:
        sl, tp = combinacion(mas)
        texto = f"SL {sl * _USD:g} / TP {tp * _USD:g} USD"
        vecinas = float(mt.combinaciones_vecinas(s.total(), lado)[mas])
    else:
        texto, vecinas = str(mas), None
    top = resumen_top(s, v, salida, tomada, lado if nombres is None else None, nombres=nombres, elegidas=fuera.elegidas)
    _columnas_consistentes(top["por_combinacion"], c, v, salida, tomada, lado if nombres is None else None)
    return Evaluacion(dentro, fuera, s.neto[np.arange(nsem), fuera.elegidas], caida, texto, vecinas if lado and nombres is None else None, top)


def resumen_top(s: mt.Semanal, valores, salida, tomada, lado: int | None, n: int = 20, nombres: list[str] | None = None, elegidas=None) -> dict:
    """Cuántas combinaciones ganan y cómo les va a las n de mayor ganancia (mirando todas las semanas).

    "por_combinacion" guarda el neto de cada combinación (total y por mitad) para la zona utilizable por grupo.
    """
    total = s.total()
    mitad = s.neto.shape[0] // 2
    primera, segunda = s.neto[:mitad].sum(0), s.neto[mitad:].sum(0)
    ops = s.operaciones.sum(0)
    top = np.argsort(-total, kind="stable")[:n]
    sub_v = np.where(tomada[:, top], valores[:, top], 0.0).astype(np.float64)
    orden = np.argsort(np.where(tomada[:, top], salida[:, top], np.iinfo(np.int64).max), axis=0, kind="stable")
    acumulado = np.cumsum(np.take_along_axis(sub_v, orden, axis=0), axis=0)
    caidas = (np.maximum.accumulate(np.maximum(acumulado, 0), axis=0) - acumulado).max(0)
    perdida = s.perdida.sum(0)[top]
    pf = np.divide(s.ganancia.sum(0)[top], perdida, out=np.full(len(top), np.nan), where=perdida > 0)
    vecinas = mt.combinaciones_vecinas(total, lado)[top] if lado else None
    meses = CONTEXTO["meses"]
    if meses is not None and len(meses) == s.neto.shape[0]:
        por_mes = np.vstack([s.neto[meses == k].sum(0) for k in range(int(meses.max()) + 1)])
    else:
        por_mes = np.empty((0, len(total)))
    return {
        "combinaciones": int(len(total)), "positivas": int((total > 0).sum()),
        "ambas_todas": int(((total > 0) & (primera > 0) & (segunda > 0)).sum()),
        "ganancia": float(total[top].mean()), "ganancia_min": float(total[top].min()), "ganancia_max": float(total[top].max()),
        "mitad1": float(primera[top].mean()), "mitad2": float(segunda[top].mean()),
        "ambas": int(((primera[top] > 0) & (segunda[top] > 0)).sum()),
        "caida": float(caidas.mean()), "pf": float(np.nanmean(pf)), "operaciones": float(ops[top].mean()),
        "vecinas": None if vecinas is None else int((vecinas > 0).sum()), "n": int(len(top)),
        "por_combinacion": {
            "total": total.astype(np.float32), "primera": primera.astype(np.float32), "segunda": segunda.astype(np.float32),
            "meses": por_mes.astype(np.float32), "nombres_meses": list(CONTEXTO["nombres_meses"]) if len(por_mes) else [],
            "lado": lado, "nombres": nombres, "elegidas": [] if elegidas is None else [int(e) for e in elegidas],
        },
    }


def consistente(pc: dict) -> np.ndarray:
    """Combinaciones que ganan en el total, en ambas mitades y en cada mes de un escenario."""
    ok = (pc["total"] > 0) & (pc["primera"] > 0) & (pc["segunda"] > 0)
    meses = pc.get("meses")
    if meses is not None and len(meses):
        ok &= (meses > 0).all(0)
    return ok


def _columnas_consistentes(pc: dict, c: Conjunto, valores, salida, tomada, lado: int | None) -> None:
    """Columnas del entregable (COLUMNAS_20) de las combinaciones consistentes en este escenario.

    Solo esas pueden ser utilizables en su grupo, así que solo se guardan esas (ahorra memoria).
    """
    indices = np.flatnonzero(consistente(pc))
    pc["columnas"] = {"indices": indices}
    if not len(indices) or not len(c):
        return
    invalidas, no_ej = CONTEXTO["conteos"]
    base_cols = mt.columnas(valores[:, indices], salida[:, indices], tomada[:, indices], c.entrada_ns, c.hora_utc_ns, c.dia,
                            max(CONTEXTO["n_dias"], int(c.dia.max()) + 1), invalidas, no_ej, True)
    for nombre in COLUMNAS_20:
        if nombre == "Combinaciones Vecinas":
            valor = mt.combinaciones_vecinas(pc["total"].astype(np.float64), lado)[indices] if lado else np.full(len(indices), np.nan)
        else:
            valor = base_cols[_RENOMBRE.get(nombre, nombre)]
        pc["columnas"][nombre] = np.asarray(valor)


def evaluar_por_operacion(c: Conjunto, elegido_fuera: np.ndarray, elegido_dentro: np.ndarray, valores, salida, nsem: int, solape: bool, signo) -> Evaluacion:
    """Cuando cada operación usa su propia combinación (ATM por grupo): mide con o sin solapamiento."""
    def medir(elegido: np.ndarray) -> tuple[mt.Calificacion, np.ndarray, float]:
        filas = np.arange(len(c))
        v = valores[filas, elegido].astype(float)
        s = salida[filas, elegido]
        toma = tomar(c.entrada_ns, s[:, None], signo)[:, 0] if solape else np.ones(len(c), dtype=bool)
        semanas = np.bincount(c.semana[toma], v[toma], nsem)
        return mt.calificar_operaciones(v[toma], c.semana[toma], nsem), semanas, _caida(v[toma], s[toma])

    dentro, _, _ = medir(elegido_dentro)
    fuera, semanas, caida = medir(elegido_fuera)
    return Evaluacion(dentro, fuera, semanas, caida, "un ATM por grupo")


def politica(c: Conjunto, valores, salida, grupos: np.ndarray | Callable[[np.ndarray], np.ndarray], nsem: int, solape: bool, signo, minimo: int = config.MUESTRA_MINIMA) -> Evaluacion:
    """Un ATM por grupo, elegido con las semanas de entrenamiento (sin solapamiento)."""
    n = len(c)

    def elegir(entreno: np.ndarray) -> np.ndarray:
        etiquetas = grupos(entreno) if callable(grupos) else grupos
        global_ = mt.elegir(valores[entreno].sum(0, dtype=np.float64), LADO)
        elegido = np.full(n, global_)
        for g in np.unique(etiquetas[etiquetas >= 0]):
            filas = entreno & (etiquetas == g)
            if filas.sum() >= minimo:
                elegido[etiquetas == g] = mt.elegir(valores[filas].sum(0, dtype=np.float64), LADO)
        return elegido

    fuera = np.zeros(n, dtype=np.int64)
    for w in range(nsem):
        prueba = c.semana == w
        fuera[prueba] = elegir(~prueba)[prueba]
    return evaluar_por_operacion(c, fuera, elegir(np.ones(n, dtype=bool)), valores, salida, nsem, solape, signo)


def tercios(x: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    def etiquetas(entreno: np.ndarray) -> np.ndarray:
        ok = entreno & ~np.isnan(x)
        cortes = np.nanquantile(x[ok], [1 / 3, 2 / 3])
        return np.where(np.isnan(x), -1, np.digitize(x, cortes))
    return etiquetas


# ---- catálogo ------------------------------------------------------------------------------------

@dataclass
class Fila:
    punto: str
    grupo: str
    forma: str
    ev: Evaluacion | None
    contratos: int = 1
    nota: str = ""
    estado: str = ""
    argumento: str = ""
    cambio: dict = field(default_factory=dict)  # filas de la Matriz que cambia frente a la referencia
    forzado: str = ""  # estado fijado de antemano: Descartada (sesgo, 2 cuentas) o No Aplica (deslizamiento)


class Catalogo:
    def __init__(self, b: Base, dias: dict[str, Dia], cal: Calendario, senales: list[Senal], medir: Callable, atr_ny: dict, avisar=print):
        self.b, self.dias, self.cal, self.senales, self.medir, self.atr_ny, self.avisar = b, dias, cal, senales, medir, atr_ny, avisar
        self.nsem = len(cal.semanas)
        self.filas: list[Fila] = []
        self.mapa: list[list] = []
        c = b.c
        self.V, self.S = matriz(c, fijo())
        self.T = tomar(c.entrada_ns, self.S, b.signo)
        self.ref = evaluar(c, self.V, self.S, self.T, self.nsem)

    def agregar(self, punto, grupo, forma, ev, contratos=1, nota="", cambio=None, forzado="") -> None:
        self.filas.append(Fila(punto, grupo, forma, ev, contratos, nota, cambio=cambio or {}, forzado=forzado))

    def subconjunto(self, mascara: np.ndarray) -> Evaluacion:
        """La referencia operando solo las señales de la máscara (se pierden las demás)."""
        c = self.b.c
        filas = np.flatnonzero(mascara)
        sub = Conjunto([c.ops[i] for i in filas], c.entrada_ns[filas], c.hora_utc_ns[filas], c.semana[filas], c.dia[filas], c.zona[filas], c.te[filas], c.compra[filas], c.minutos[filas])
        t = tomar(sub.entrada_ns, self.S[filas], self.b.signo[filas])
        return evaluar(sub, self.V[filas], self.S[filas], t, self.nsem)

    # 1. ATM fijo frente a variable
    def gestion(self) -> None:
        c, m = self.b.c, Minutos(REF[3])
        self.agregar("1", "Salida", "ATM fijo (referencia)", self.ref, cambio={})
        for nivel in config.BREAKEVEN_TICKS:
            v, s = matriz(c, lambda op, n=nivel: salidas.breakeven(op, m, n)[:2])
            self.agregar("1", "Salida", f"Breakeven en +{nivel} ticks ({nivel * _USD:g} USD)", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem), cambio={"Gestión": f"Breakeven en +{nivel * _USD:g} USD"})
        v, s = matriz(c, lambda op: salidas.sl_tiempo(op, m))
        self.agregar("1", "Salida", "SL que se acerca al cerrar cada vela", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem), cambio={"Gestión": "SL que se acerca cada vela"})
        v, s = matriz(c, lambda op: sf.trailing_velas(op, REF[3]))
        self.agregar("1", "Salida", "Trailing por velas (SL al extremo de la vela que cierra a favor)", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem), cambio={"Gestión": "Trailing por velas"})
        for nombre, funcion in salidas.OTRAS_SALIDAS.items():
            if nombre.startswith("SL/TP fijos"):
                continue
            nombres_ = funcion(c.ops[0], m)[2]
            v, s = matriz(c, lambda op, f=funcion: f(op, m)[:2], len(nombres_))
            contratos = 2 if "parcial" in nombre.lower() else 1
            self.agregar("1", "Salida", nombre, evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem, None, nombres_), contratos, "USD por contrato" if contratos == 2 else "", {"Gestión": nombre})
        for extra in (3, 6, 9):
            v, s = matriz(c, lambda op, e=extra: sf.condicional(op, REF[3], e))
            self.agregar("Nueva", "Salida", f"Cierre condicionado: si gana a los {REF[3]} min, SL a la entrada y {extra} min más", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem), cambio={"Cierre por tiempo": f"{REF[3]} min; si va ganando, SL a la entrada y {extra} min más"})
        for revisa in (2, 4):
            for umbral in (60, 100):
                v, s = matriz(c, lambda op, r=revisa, u=umbral: sf.corte_temprano(op, REF[3], r, u))
                self.agregar("Nueva", "Salida", f"Corte temprano: a los {revisa} min, si va {umbral} ticks o más en contra, salir", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem), cambio={"Gestión": f"Salir a los {revisa} min si va −{umbral} ticks"})
        contrarias = self._contrarias()
        v, s = matriz(c, lambda op: sf.contraria(op, REF[3], contrarias.get(op.fila)))
        self.agregar("Nueva", "Salida", "Salir cuando confirma una señal contraria de tu registro", evaluar(c, v, s, tomar(c.entrada_ns, s, self.b.signo), self.nsem),
                     nota="Descartada por sesgo: una señal contraria solo está en tu registro si su orden se ejecutó después (las demás se borraban); usarla es conocer el futuro. Se mide con señales registradas sin borrar.",
                     cambio={"Disparo del cierre": "También al confirmar una señal contraria"}, forzado=DESCARTADA)

    def _contrarias(self) -> dict[int, int]:
        """Índice del tick de salida por la primera señal contraria que confirma con la posición abierta."""
        horas = [(ns_del_dia(s.fecha, s.hora_utc_s), signo_de(s)) for s in self.senales if s.fecha and s.hora_utc_s is not None and s.tipo in config.VALORES_TIPO]
        horas.sort()
        tiempos = np.array([h for h, _ in horas])
        signos = np.array([g for _, g in horas])
        salida = {}
        for op in self.b.c.ops:
            signo = 1 if op.tipo == "Buy" else -1
            i, j = np.searchsorted(tiempos, [op.entrada_ns + 1, op.entrada_ns + int(REF[3] * _NS_MIN)])
            contra = np.flatnonzero(signos[i:j] == -signo)
            if contra.size:
                t = tiempos[i + contra[0]] + REF[1] * 1_000_000
                salida[op.fila] = min(int(np.searchsorted(op.ns, t)), len(op.ns) - 1)
        return salida

    # 2. Solapamiento
    def solapamiento(self) -> None:
        c = self.b.c
        for maximo, texto in ((2, "hasta 2"), (3, "hasta 3"), (99, "sin límite")):
            t = tomar(c.entrada_ns, self.S, self.b.signo, maximo)
            self.agregar("2", "Posición", f"Varias posiciones en la misma dirección ({texto})", evaluar(c, self.V, self.S, t, self.nsem), maximo, "Varios contratos a la vez", {"Solapamiento": f"Misma dirección, {texto} a la vez"})
        for minutos in (2, 5, 10):
            t = tomar(c.entrada_ns, self.S, self.b.signo, 1, separacion_ns=minutos * _NS_MIN)
            self.agregar("Nueva", "Selección", f"Separación mínima de {minutos} min entre entradas", evaluar(c, self.V, self.S, t, self.nsem), cambio={"Selección": f"{minutos} min mínimo entre entradas"})

    # 3, 4, 5 y 15. Grupos
    def grupos(self) -> None:
        c, sg = self.b.c, self.b.signo
        zonas = np.array(self.cal.zonas)
        m_col = np.array([str(self.b.meds[o.fila].senal.crudo.get("M", "-")).strip() for o in c.ops])
        m_codigos = sorted(set(m_col))
        m_idx = np.array([m_codigos.index(x) for x in m_col])
        self.b.etiquetas["M"] = m_col
        for solape in (True, False):
            texto = "con solapamiento" if solape else "sin solapamiento"
            self.agregar("3", "Selección", f"Un ATM por Zona Reacción ({texto})", politica(c, self.V, self.S, c.zona, self.nsem, solape, sg), 1 if solape else 99,
                         "" if solape else "Descartada: requiere 2 cuentas. Sin solapamiento hay varias posiciones a la vez, incluso compra y venta, y NinjaTrader las compensa en una sola cuenta.",
                         {"ATM": f"Uno por Zona Reacción ({texto})"}, "" if solape else DESCARTADA)
        self.agregar("5", "Adaptación", "Un ATM por estructura M (A, B, LA, LM, LP)", politica(c, self.V, self.S, m_idx, self.nsem, True, sg), cambio={"ATM": "Uno por estructura M"})
        self.agregar("Nueva", "Adaptación", "Un ATM por Te", politica(c, self.V, self.S, c.te - 1, self.nsem, True, sg), cambio={"ATM": "Uno por Te"})
        for z, nombre in enumerate(zonas):
            self.agregar("4", "Selección", f"Dejar de operar {nombre}", self.subconjunto(c.zona != z), cambio={"Selección": f"Sin {nombre}"})
        quitar = [i for i, n in enumerate(zonas) if n in ("Trend ≥ 2do Pivot", "V")]
        self.agregar("4", "Selección", "Dejar de operar Trend ≥ 2do Pivot y V", self.subconjunto(~np.isin(c.zona, quitar)), cambio={"Selección": "Sin Trend ≥ 2do Pivot ni V"})
        for z, nombre in enumerate(zonas):
            for te in (1, 2):
                par = (c.zona == z) & (c.te == te)
                if 0 < par.sum() < len(c):
                    self.agregar("4", "Selección", f"Dejar de operar {nombre} en Te {te} ({int(par.sum())} señales)", self.subconjunto(~par), cambio={"Selección": f"Sin {nombre} en Te {te}"})
        for codigo in m_codigos:
            self.agregar("15", "Selección", f"Dejar de operar con estructura M = {codigo}", self.subconjunto(m_col != codigo), cambio={"Selección": f"Sin M = {codigo}"})
        compra = c.compra
        reglas_m = {
            "No operar Buy en estructura bajista (B)": ~(compra & (m_col == "B")),
            "No operar Sell en estructura alcista (A)": ~(~compra & (m_col == "A")),
            "Solo a favor de la estructura (Buy en A, Sell en B; laterales ambas)": ~((compra & (m_col == "B")) | (~compra & (m_col == "A"))),
            "Solo contra la estructura (Buy en B, Sell en A; laterales ambas)": ~((compra & (m_col == "A")) | (~compra & (m_col == "B"))),
        }
        for nombre, mascara in reglas_m.items():
            self.agregar("15", "Selección", nombre, self.subconjunto(mascara), cambio={"Selección": nombre})
        ohlc = np.array([str(self.b.meds[o.fila].senal.ohlc) for o in c.ops])
        self.agregar("Nueva", "Selección", f"No operar órdenes calculadas sobre el Close ({int((ohlc == 'Close').sum())} señales)", self.subconjunto(ohlc != "Close"), cambio={"Selección": "Sin órdenes sobre el Close"})

    # 5 y 15. Mercado: indicadores, dirección, adaptación
    def mercado(self) -> None:
        c, sg = self.b.c, self.b.signo
        velas = cargar_velas(config.CARPETA_DATA_TICKS, config.CARPETA_VELAS_SESION, self.avisar)
        series = {te: indicadores_serie(velas, te) for te in config.VALORES_TE}
        ind = _indicadores(c, velas, series, _serie_de_dia(), self.atr_ny, self.dias)
        for nombre, x in ind.items():
            if nombre == "Minutos desde la apertura":
                continue
            self.agregar("5", "Adaptación", f"ATM según tercio de {nombre}", politica(c, self.V, self.S, tercios(x), self.nsem, True, sg), cambio={"ATM": f"Según tercio de {nombre}"})
            self.agregar("15", "Selección", f"No operar el tercio de {nombre} que perdió en las otras semanas", self._filtro_aprendido(tercios(x)), cambio={"Selección": f"Filtro por {nombre}"})
        dia_mov, quince = self._direccion()
        for nombre, mascara, cambio in (
            ("Solo señales a favor del movimiento desde la apertura", dia_mov > 0, "A favor del día"),
            ("Solo señales contra el movimiento desde la apertura", dia_mov < 0, "Contra el día"),
            ("Solo señales a favor de los últimos 15 minutos", quince > 0, "A favor de los últimos 15 min"),
            ("Solo señales contra los últimos 15 minutos", quince < 0, "Contra los últimos 15 min"),
        ):
            self.agregar("15", "Selección", nombre, self.subconjunto(mascara), cambio={"Selección": cambio})
        atr = np.array([np.nan if self.atr_ny.get(o.fila) is None else self.atr_ny[o.fila] for o in c.ops])
        factores = np.round(np.arange(0.3, 2.01, 0.1), 2)
        pos = self._pos
        v, s = matriz(c, lambda op: sf.tp_proporcional(op, REF[3], atr[pos[op.fila]], factores), LADO * len(factores))
        nombres_ = [f"SL {sl * _USD:g} USD · TP {f:g} × ATR NY" for sl in config.SIM_TICKS for f in factores]
        self.agregar("5", "Adaptación", "TP proporcional al ATR NY y SL fijo", evaluar(c, v, s, tomar(c.entrada_ns, s, sg), self.nsem, None, nombres_), cambio={"ATM": "TP = factor × ATR NY, SL fijo"})
        self._semanal_movil()
        self._dentro_del_dia()
        self._pausa()

    def _filtro_aprendido(self, grupos_fn) -> Evaluacion:
        """Deja de operar el grupo que perdió (con la combinación más elegida) en las semanas de entrenamiento."""
        c = self.b.c
        mas = Counter(self.ref.fuera.elegidas).most_common(1)[0][0]
        deja = np.ones(len(c), dtype=bool)
        for w in range(self.nsem):
            entreno = c.semana != w
            g = grupos_fn(entreno)
            for k in np.unique(g[g >= 0]):
                filas = entreno & (g == k)
                if filas.sum() >= config.MUESTRA_MINIMA and self.V[filas, mas].mean() < 0:
                    deja[(c.semana == w) & (g == k)] = False
        return self.subconjunto(deja)

    def _direccion(self) -> tuple[np.ndarray, np.ndarray]:
        c = self.b.c
        dia_mov, quince = np.zeros(len(c)), np.zeros(len(c))
        for k, op in enumerate(c.ops):
            d = self.dias[op.clave_dia]
            signo = 1 if op.tipo == "Buy" else -1
            i_t = int(np.searchsorted(d.ns, op.hora_utc_ns)) - 1
            i_a = int(np.searchsorted(d.ns, d.apertura_ns))
            i_15 = max(int(np.searchsorted(d.ns, op.hora_utc_ns - 15 * _NS_MIN)), 0)
            dia_mov[k] = signo * (int(d.last[i_t]) - int(d.last[i_a]))
            quince[k] = signo * (int(d.last[i_t]) - int(d.last[i_15]))
        return dia_mov, quince

    @property
    def _pos(self) -> dict[int, int]:
        return {o.fila: k for k, o in enumerate(self.b.c.ops)}

    def _semanal_movil(self) -> None:
        """Cambiar de ATM cada semana con las 4 semanas anteriores (sin mirar el futuro)."""
        c = self.b.c
        s = mt.semanal(self.V, self.T, c.semana, self.nsem)
        elegidas = [mt.elegir(s.neto[max(0, w - 4):w].sum(0), LADO) for w in range(self.nsem)]
        semanas = s.neto[np.arange(self.nsem), elegidas]
        semanas[0] = 0.0  # sin historia: no se opera la primera semana
        neto = semanas.sum()
        gan, per = s.ganancia[np.arange(self.nsem), elegidas][1:].sum(), s.perdida[np.arange(self.nsem), elegidas][1:].sum()
        mitad = self.nsem // 2
        cal = mt.Calificacion(float(neto), int(s.operaciones[np.arange(self.nsem), elegidas][1:].sum()), float(gan / per) if per else float("nan"), int((semanas > 0).sum()), float(semanas[:mitad].sum()), float(semanas[mitad:].sum()), tuple(elegidas))
        self.agregar("5", "Adaptación", "Cambiar de ATM cada semana según las 4 semanas anteriores", Evaluacion(cal, cal, semanas, float("nan"), "variable"), nota="Sin mirar el futuro; la primera semana no se opera", cambio={"ATM": "El mejor de las 4 semanas anteriores"})

    def _dentro_del_dia(self) -> None:
        """Si la primera operación del día pierde, el resto del día usa otro ATM (o no se opera)."""
        c = self.b.c
        mas = Counter(self.ref.fuera.elegidas).most_common(1)[0][0]
        alternativas = {"SL 118 / TP 50,5 USD": (236, 101), "SL 92,5 / TP 50,5 USD": (185, 101), "no operar más ese día": None}
        filas = np.arange(len(c))
        resultados = {}
        for nombre, atm in alternativas.items():
            alt = None if atm is None else _TICKS_IDX(atm)
            v, s, toma = np.zeros(len(c)), np.zeros(len(c), dtype=np.int64), np.zeros(len(c), dtype=bool)
            libre, dia, perdio = np.iinfo(np.int64).min, -1, False
            for k in np.argsort(c.entrada_ns, kind="stable"):
                if c.dia[k] != dia:
                    dia, perdio, primera = c.dia[k], False, True
                else:
                    primera = False
                col = mas if not perdio else alt
                if col is None or c.entrada_ns[k] < libre:
                    continue
                v[k], s[k], toma[k] = self.V[k, col], self.S[k, col], True
                libre = s[k]
                if primera and v[k] < 0:
                    perdio = True
            resultados[nombre] = (v, s, toma)
        semanas = {n: np.bincount(c.semana[t], v[t], self.nsem) for n, (v, s, t) in resultados.items()}
        nombres = list(resultados)
        elegido = [nombres[int(np.argmax([semanas[n].sum() - semanas[n][w] for n in nombres]))] for w in range(self.nsem)]
        sem = np.array([semanas[elegido[w]][w] for w in range(self.nsem)])
        valores = np.concatenate([resultados[elegido[w]][0][(c.semana == w) & resultados[elegido[w]][2]] for w in range(self.nsem)])
        semana_v = np.concatenate([np.full(((c.semana == w) & resultados[elegido[w]][2]).sum(), w) for w in range(self.nsem)])
        fuera = mt.calificar_operaciones(valores, semana_v, self.nsem)
        mejor = max(nombres, key=lambda n: semanas[n].sum())
        v, s, t = resultados[mejor]
        dentro = mt.calificar_operaciones(v[t], c.semana[t], self.nsem)
        self.agregar("Nueva", "Adaptación", "Adaptación dentro del día: si la primera operación pierde, cambiar de ATM", Evaluacion(dentro, fuera, sem, _caida(v[t], s[t]), Counter(elegido).most_common(1)[0][0]), cambio={"ATM": "Cambia si la primera operación del día pierde"})

    def _pausa(self) -> None:
        """Dejar de operar mientras la suma de las últimas N operaciones (reales o virtuales) sea negativa."""
        c = self.b.c
        for n_ult in (10, 20):
            tomada = np.zeros_like(self.T)
            historial = np.zeros((n_ult, self.V.shape[1]))
            libre = np.full(self.V.shape[1], np.iinfo(np.int64).min)
            for i, k in enumerate(np.argsort(c.entrada_ns, kind="stable")):
                activa = historial.sum(0) >= 0 if i >= n_ult else np.ones(self.V.shape[1], dtype=bool)
                puede = c.entrada_ns[k] >= libre
                tomada[k] = puede & activa
                libre = np.where(puede, self.S[k], libre)  # la operación virtual también ocupa el tiempo
                historial[i % n_ult] = np.where(puede, self.V[k], 0)
            self.agregar("16", "Adaptación", f"Pausa si las últimas {n_ult} operaciones suman negativo", evaluar(c, self.V, self.S, tomada, self.nsem), nota="Se siguen contando operaciones virtuales para saber cuándo volver", cambio={"Selección": f"Pausa si las últimas {n_ult} suman negativo"})

    # 10, 11, 12, 13. Ejecución
    def ejecucion(self) -> None:
        c, sg, med = self.b.c, self.b.signo, list(self.b.meds.values())
        for desliz in (0, 1, 2, 4, 5, 6):
            b = base(med, self.dias, self.cal, ajuste=lambda m, d=desliz: d - REF[2])
            v, s = matriz(b.c, fijo())
            self.agregar("10", "Entrada", f"Deslizamiento de entrada de {desliz} ticks", evaluar(b.c, v, s, tomar(b.c.entrada_ns, s, b.signo), self.nsem), nota="No aplica: no es una decisión, es el costo de ejecutar con más o menos deslizamiento.", cambio={"Deslizamiento de entrada": f"± {desliz} ticks"}, forzado=NO_APLICA)
        b = base(med, self.dias, self.cal, ancla_orden=True)
        v, s = matriz(b.c, fijo())
        v = v - REF[2] * _USD  # el resultado sigue pagando el deslizamiento real
        self.agregar("10", "Entrada", "SL y TP medidos desde el precio de la orden (no desde el de entrada)", evaluar(b.c, v, s, tomar(b.c.entrada_ns, s, b.signo), self.nsem), cambio={"ATM": "SL/TP desde el precio de la orden"})
        salto = np.array([signo_de(self.b.meds[o.fila].senal) * (int(self.dias[o.clave_dia].last[self.b.meds[o.fila].indice]) - self.b.meds[o.fila].precio_op) for o in c.ops])
        for maximo in (0, 1, 2):
            self.agregar("11", "Entrada", f"Stop límite: no entrar si el tick que dispara salta más de {maximo} ticks ({int((salto > maximo).sum())} señales)", self.subconjunto(salto <= maximo), cambio={"Disparo de la orden pendiente": f"Stop límite, salto máximo {maximo} ticks"})
        distancia = self._distancia_cierre()
        for maximo in (30, 60, 90):
            self.agregar("Nueva", "Selección", f"No operar si la orden está a más de {maximo} ticks del cierre de la vela", self.subconjunto(distancia <= maximo), cambio={"Selección": f"Orden a ≤ {maximo} ticks del cierre"})
        continuacion = np.array([z in config.ZONAS_CONTINUACION for z in np.array(self.cal.zonas)[c.zona]])
        for nombre, prioridad in (
            ("Prioridad a Te 2 cuando entran a la vez", -c.te), ("Prioridad a Te 1 cuando entran a la vez", c.te),
            ("Prioridad a zonas de continuación cuando entran a la vez", ~continuacion), ("Prioridad a zonas de impulso cuando entran a la vez", continuacion),
            ("Prioridad a Buy cuando entran a la vez", ~c.compra), ("Prioridad a Sell cuando entran a la vez", c.compra),
        ):
            orden = orden_con_prioridad(c.entrada_ns, prioridad.astype(np.int64))
            punto = "13" if "Buy" in nombre or "Sell" in nombre else "12"
            self.agregar(punto, "Posición", nombre, evaluar(c, self.V, self.S, tomar(c.entrada_ns, self.S, sg, orden=orden), self.nsem), cambio={"Prioridad": nombre.replace(" cuando entran a la vez", "")})
        pares = [(236, 101), (236, 128), (179, 131)]
        mas = Counter(self.ref.fuera.elegidas).most_common(1)[0][0]
        v2 = np.stack([self.V[:, mas] + self.V[:, _TICKS_IDX(p)] for p in pares], axis=1) / 2
        s2 = np.stack([np.maximum(self.S[:, mas], self.S[:, _TICKS_IDX(p)]) for p in pares], axis=1)
        nombres_ = [f"{_texto(mas)} + SL {p[0] * _USD:g} / TP {p[1] * _USD:g} USD" for p in pares]
        self.agregar("Nueva", "Posición", "Dos ATM a la vez (2 contratos)", evaluar(c, v2, s2, tomar(c.entrada_ns, s2, sg), self.nsem, None, nombres_), 2, "USD por contrato", {"ATM": "Dos ATM, 2 contratos"})
        atr = np.array([np.nan if self.atr_ny.get(o.fila) is None else self.atr_ny[o.fila] for o in c.ops])
        corte = np.nanquantile(atr, 1 / 3)
        peso = np.where(atr <= corte, 2.0, 1.0)
        self.agregar("Nueva", "Posición", "Tamaño por riesgo: 2 contratos en días tranquilos (tercio bajo del ATR NY)", evaluar(c, self.V, self.S, self.T, self.nsem, peso=peso), 2, "USD totales", {"Tamaño": "2 contratos si el ATR NY es bajo"})

    def _distancia_cierre(self) -> np.ndarray:
        d = np.zeros(len(self.b.c))
        for k, op in enumerate(self.b.c.ops):
            m = self.b.meds[op.fila]
            _, cierre = precio_base_y_cierre(m.senal, self.dias[op.clave_dia])
            d[k] = signo_de(m.senal) * (m.precio_op - cierre)
        return d

    # Formas que faltan por medir (falta un dato)
    def no_medidas(self) -> None:
        borradas = ("Faltan las señales cuya orden no se ejecutaba: se borraban del registro, así que sin ellas solo se verían las que ya se sabe que se ejecutaron. "
                    "Se mide cuando registres también las señales no ejecutadas.")
        self.filas.append(Fila("9", "Entrada", "Alargar la ventana de ejecución", None, estado=NO_MEDIDA, argumento=borradas,
                               cambio={"Ventana de ejecución": "Más velas"}))
        self.filas.append(Fila("Nueva", "Entrada", "Entrar a mercado o antes de la orden pendiente", None, estado=NO_MEDIDA, argumento=borradas,
                               cambio={"Disparo de la orden pendiente": "A mercado al confirmar"}))
        self.filas.append(Fila("15", "Adaptación", "ATM o filtro según la volatilidad implícita (VIX/VXN)", None, estado=NO_MEDIDA,
                               argumento="Falta la serie de VIX/VXN de julio a octubre de 2026. Se mide si la descargas (diaria o de 1 minuto).",
                               cambio={"ATM": "Según VIX/VXN"}))

    # 14. Noticias
    def noticias(self) -> None:
        eventos = leer_calendario()
        if not eventos:
            self.filas.append(Fila("14", "Selección", "No operar en noticias de impacto alto", None, estado=NO_MEDIDA, argumento="Falta el calendario de noticias: entrada/calendario_noticias.csv está vacío. Se mide en cuanto lo completes con las noticias de carpeta roja / 3 estrellas.",
                                   cambio={"Selección": "Sin noticias de impacto alto"}))
            return
        c = self.b.c
        dia_op = np.array([o.clave_dia for o in c.ops])
        con_noticia = {e[0] for e in eventos}
        hora_ny = lambda e: e[1].hour * 60 + e[1].minute
        dias_830 = {e[0] for e in eventos if hora_ny(e) <= 9 * 60 + 30}
        dias_10 = {e[0] for e in eventos if hora_ny(e) > 9 * 60 + 30}
        cerca = np.zeros(len(c), dtype=bool)
        for k, op in enumerate(c.ops):
            for fecha, ny_dt, _ in eventos:
                if fecha != op.clave_dia:
                    continue
                delta = (op.entrada_ns - _ns_ny(ny_dt)) / _NS_MIN
                cerca[k] |= -5 <= delta <= 15
        for nombre, mascara, cambio in (
            ("No operar los días con noticia de impacto alto", ~np.isin(dia_op, list(con_noticia)), "Sin días con noticia"),
            ("No operar de 5 min antes a 15 min después de la noticia", ~cerca, "Sin −5/+15 min de la noticia"),
            ("No operar los días con noticia antes de la apertura (8:30)", ~np.isin(dia_op, list(dias_830)), "Sin días con noticia de 8:30"),
            ("No operar los días con noticia dentro de tu hora (10:00)", ~np.isin(dia_op, list(dias_10)), "Sin días con noticia de 10:00"),
        ):
            self.agregar("14", "Selección", nombre, self.subconjunto(mascara), cambio={"Selección": cambio})

    # 6, 7, 8, 9. Mapa de reglas combinadas y ventana
    def mapa_reglas(self) -> None:
        quitar = [i for i, n in enumerate(self.cal.zonas) if n in ("Trend ≥ 2do Pivot", "V")]
        for distancia in config.FORMAS_DISTANCIAS:
            for demora in config.FORMAS_COLOCACION:
                self.avisar(f"  Mapa: distancia {distancia}, colocación {demora} ms...")
                meds = self.medir(Escenario(90 + distancia, distancia, demora, REF[2], config.LIMITE_REENTRADA_PRINCIPAL))
                b = base(meds, self.dias, self.cal)
                for minutos in config.FORMAS_CIERRES:
                    v, s = matriz(b.c, fijo(minutos))
                    for zonas_txt, mascara in (("Todas", np.ones(len(b.c), dtype=bool)), ("Sin Trend ≥ 2do Pivot ni V", ~np.isin(b.c.zona, quitar))):
                        filas = np.flatnonzero(mascara)
                        sub = Conjunto([b.c.ops[i] for i in filas], b.c.entrada_ns[filas], b.c.hora_utc_ns[filas], b.c.semana[filas], b.c.dia[filas], b.c.zona[filas], b.c.te[filas], b.c.compra[filas], b.c.minutos[filas])
                        ev = evaluar(sub, v[filas], s[filas], tomar(sub.entrada_ns, s[filas], b.signo[filas]), self.nsem)
                        self.mapa.append([distancia, demora, minutos, zonas_txt, len(filas), ev])
        for nombre, ventanas, cambio in (
            ("Ventana: zonas de impulso Te 2 con 1 min en vez de 2", {(True, 2): 1}, "Impulso Te 2: 1 min"),
            ("Ventana: zonas de continuación Te 2 con 3 min en vez de 4", {(False, 2): 3}, "Continuación Te 2: 3 min"),
            ("Ventana: Te 2 con 1 minuto menos en ambos tipos", {(True, 2): 1, (False, 2): 3}, "Te 2: −1 min"),
        ):
            meds = self.medir(Escenario(1, REF[0], REF[1], REF[2], config.LIMITE_REENTRADA_PRINCIPAL), ventanas)
            b = base(meds, self.dias, self.cal)
            v, s = matriz(b.c, fijo())
            self.agregar("9", "Entrada", nombre, evaluar(b.c, v, s, tomar(b.c.entrada_ns, s, b.signo), self.nsem), nota="Alargar la ventana no se puede medir: faltan las señales borradas", cambio={"Ventana de ejecución": cambio})

    # Azar
    def azar(self) -> np.ndarray:
        c = self.b.c
        rng = np.random.default_rng(config.AZAR_SEMILLA)
        netos = []
        for i in range(config.FORMAS_AZAR):
            if i % 20 == 0:
                self.avisar(f"  Carteras al azar {i}/{config.FORMAS_AZAR}...")
            ca = conjunto(al_azar(c, self.dias, rng, REF[1], REF[2]), self.dias, self.cal)
            v, s = matriz(ca, fijo())
            sg = np.array([1 if o.tipo == "Buy" else -1 for o in ca.ops])
            netos.append(evaluar(ca, v, s, tomar(ca.entrada_ns, s, sg), self.nsem).fuera.neto)
        return np.array(netos)


_TICKS = list(config.SIM_TICKS)


def _TICKS_IDX(par: tuple[int, int]) -> int:
    return _TICKS.index(par[0]) * LADO + _TICKS.index(par[1])


def _texto(indice: int) -> str:
    sl, tp = combinacion(indice)
    return f"SL {sl * _USD:g} / TP {tp * _USD:g} USD"


def _ns_ny(momento: datetime) -> int:
    from zoneinfo import ZoneInfo
    return int(momento.replace(tzinfo=ZoneInfo(config.ZONA_HORARIA_NY)).timestamp()) * 1_000_000_000


def leer_calendario() -> list[tuple[str, datetime, str]]:
    """(clave del día, fecha y hora de Nueva York, noticia) de entrada/calendario_noticias.csv."""
    ruta = config.CALENDARIO_NOTICIAS
    if not ruta.exists():
        return []
    eventos = []
    with ruta.open(encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            if not fila.get("fecha"):
                continue
            momento = datetime.strptime(f"{fila['fecha'].strip()} {fila['hora_ny'].strip()}", "%Y-%m-%d %H:%M")
            eventos.append((momento.strftime("%Y%m%d"), momento, fila.get("noticia", "").strip()))
    return eventos
