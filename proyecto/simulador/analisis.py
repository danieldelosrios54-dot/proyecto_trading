"""Pestañas de analisis_combinaciones.xlsx: preguntas 1 a 8 y análisis añadidos.

"Dentro" elige mirando todas las semanas; "Fuera" elige con 13 semanas y mide la que falta, 14 veces.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

import config
from medicion.analisis import Tabla
from simulador import metricas as mt
from simulador.datos import LADO, Conjunto, al_azar, combinacion, conjunto, inversas, matriz, matriz_lista
from simulador.reglas_dia import aplicar, reglas
from simulador.salidas import OTRAS_SALIDAS

_TICKS = np.array(config.SIM_TICKS)
_SL = np.repeat(_TICKS, LADO)
_TP = np.tile(_TICKS, LADO)
_USD = config.USD_POR_TICK


def _usd(ticks: float) -> float:
    return round(ticks * _USD, 2)


def _r(x: float | None, d: int = 2) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), d)


@dataclass
class Forma:
    nombre: str
    tipo: str
    velas: int
    dentro: mt.Calificacion
    fuera: mt.Calificacion
    combinacion: str
    nota: str = ""


def _texto_combinacion(indice: int) -> str:
    sl, tp = combinacion(indice)
    return f"SL {_usd(sl)} / TP {_usd(tp)} USD"


def _mas_elegida(fuera: mt.Calificacion) -> int:
    return Counter(fuera.elegidas).most_common(1)[0][0]


def _bloque_calificacion(prefijo: str) -> list[str]:
    return [f"{prefijo}: neto (USD)", f"{prefijo}: PF", f"{prefijo}: operaciones", f"{prefijo}: semanas positivas", f"{prefijo}: primera mitad", f"{prefijo}: segunda mitad"]


def _valores_calificacion(c: mt.Calificacion) -> list:
    return [_r(c.neto), _r(c.pf), c.operaciones, c.semanas_positivas, _r(c.mitad1), _r(c.mitad2)]


def _resumen_grid(s: mt.Semanal) -> list:
    """Positivas, % positivas, ambas mitades, mediana de esperanza, mejor meseta y su resultado."""
    pos, ambas = mt.positivas(s)
    total, ops = s.total(), s.operaciones.sum(0)
    esperanza = np.divide(total, ops, out=np.full(len(total), np.nan), where=ops > 0)
    mejor = mt.elegir(total, LADO)
    sl, tp = combinacion(mejor)
    pf = s.ganancia.sum(0)[mejor] / s.perdida.sum(0)[mejor] if s.perdida.sum(0)[mejor] else float("nan")
    return [pos, _r(100 * pos / len(total), 1), ambas, _r(np.nanmedian(esperanza)), _usd(sl), _usd(tp), _r(total[mejor]), _r(pf), int(ops[mejor])]


_ENC_RESUMEN = [
    "Combinaciones positivas", "% positivas", "Positivas en ambas mitades", "Mediana de Esperanza (USD)",
    "Mejor zona: SL (USD)", "Mejor zona: TP (USD)", "Mejor zona: neto (USD)", "Mejor zona: PF", "Mejor zona: operaciones",
]


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    ok = ~np.isnan(a) & ~np.isnan(b)
    if ok.sum() < 10:
        return None
    ra = np.argsort(np.argsort(a[ok])).astype(float)
    rb = np.argsort(np.argsort(b[ok])).astype(float)
    return round(float(np.corrcoef(ra, rb)[0, 1]), 2)


class Analisis:
    def __init__(self, conjuntos: dict[int, Conjunto], n_semanas: int, zonas: list[str], semanas: list, dias: dict, avisar=print):
        self.c = conjuntos
        self.nsem = n_semanas
        self.zonas = zonas
        self.semanas = semanas
        self.dias = dias
        self.avisar = avisar
        self.formas: list[Forma] = []
        self.tablas: dict[str, Tabla] = {}
        self.k4: dict[int, tuple] = {}  # escenario -> (matriz, tomada) con el cierre de los entregables
        self.semanal_e1: dict[int, mt.Semanal] = {}
        self.totales: dict[tuple[int, int], np.ndarray] = {}
        self.fuera_grid: dict[tuple[int, int], mt.Calificacion] = {}

    # ---- utilidades ------------------------------------------------------------------------

    def _tomar(self, c: Conjunto, salida_ns: np.ndarray) -> np.ndarray:
        return mt.tomar_sin_solape(c.entrada_ns, salida_ns)

    def _semanal(self, c: Conjunto, valores, tomada, filas=None) -> mt.Semanal:
        if filas is None:
            return mt.semanal(valores, tomada, c.semana, self.nsem)
        return mt.semanal(valores[filas], None if tomada is None else tomada[filas], c.semana[filas], self.nsem)

    def _sumas(self, c: Conjunto, valores: np.ndarray, etiquetas: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Sumas y cuentas por grupo y semana: (grupos, semanas, combinaciones) y (grupos, semanas)."""
        grupos = int(etiquetas.max()) + 1 if (etiquetas >= 0).any() else 0
        validas = etiquetas >= 0
        clave = etiquetas[validas] * self.nsem + c.semana[validas]
        uno = np.zeros((grupos * self.nsem, len(c)), dtype=np.float32)
        uno[clave, np.flatnonzero(validas)] = 1.0
        sumas = (uno @ valores).reshape(grupos, self.nsem, -1)
        cuentas = np.bincount(clave, minlength=grupos * self.nsem).reshape(grupos, self.nsem)
        return sumas, cuentas

    def _politica(self, c: Conjunto, valores, salida_ns, grupos: np.ndarray | Callable[[np.ndarray], np.ndarray], minimo=config.MUESTRA_MINIMA):
        """Elige un ATM por grupo con las semanas de entrenamiento (sin solapamiento) y mide con solapamiento.

        `grupos` son etiquetas fijas o una función que las calcula solo con las semanas de entrenamiento.
        Un grupo con menos de `minimo` señales de entrenamiento usa el ATM general.
        """
        n = len(c)
        por_semana, _ = self._sumas(c, valores, np.zeros(n, dtype=np.int64))
        por_semana = por_semana[0]
        fijas = None if callable(grupos) else (grupos, *self._sumas(c, valores, grupos))

        def elegir(fuera: int | None) -> np.ndarray:
            if fijas is None:
                entreno = np.ones(n, dtype=bool) if fuera is None else c.semana != fuera
                etiquetas = grupos(entreno)
                sumas, cuentas = self._sumas(c, valores, etiquetas)
            else:
                etiquetas, sumas, cuentas = fijas
            if fuera is None:
                total_g, cuenta_g, total = sumas.sum(1), cuentas.sum(1), por_semana.sum(0)
            else:
                total_g = sumas.sum(1) - sumas[:, fuera]
                cuenta_g = cuentas.sum(1) - cuentas[:, fuera]
                total = por_semana.sum(0) - por_semana[fuera]
            global_ = mt.elegir(total.astype(np.float64), LADO)
            elegido = np.full(n, global_)
            for g in range(len(total_g)):
                if cuenta_g[g] >= minimo:
                    elegido[etiquetas == g] = mt.elegir(total_g[g].astype(np.float64), LADO)
            return elegido

        def medir(elegido: np.ndarray) -> mt.Calificacion:
            v = valores[np.arange(n), elegido].astype(np.float64)
            s = salida_ns[np.arange(n), elegido]
            tomadas = aplicar(v, c.entrada_ns, s, c.dia, None)
            return mt.calificar_operaciones(v[tomadas], c.semana[tomadas], self.nsem)

        dentro = medir(elegir(None))
        elegido = np.zeros(n, dtype=np.int64)
        for w in range(self.nsem):
            prueba = c.semana == w
            elegido[prueba] = elegir(w)[prueba]
        return dentro, medir(elegido)

    # ---- escenario 1, todos los cierres -----------------------------------------------------

    def escenario1(self) -> None:
        c = self.c[1]
        filas_p1, filas_p2, filas_p3, filas_rat, filas_p5, filas_p6, filas_otras = [], [], [], [], [], [], []
        subconjuntos = {"Todas": None, "Te 1": c.te == 1, "Te 2": c.te == 2, "Buy": c.compra, "Sell": ~c.compra}
        ratio = _TP / _SL
        grupos_ratio = {"TP menor que SL (ratio < 1)": ratio < 1, "TP igual a SL (ratio = 1)": ratio == 1, "TP mayor que SL (ratio > 1)": ratio > 1}
        for velas in config.SIM_VELAS:
            self.avisar(f"  Escenario 1, cierre a {velas} velas...")
            m = matriz(c, velas)
            t = self._tomar(c, m.salida_ns)
            s = self._semanal(c, m.valores, t)
            self.semanal_e1[velas] = s
            self.totales[(1, velas)] = s.total()
            dentro, fuera = mt.dentro_de_muestra(s, LADO), mt.fuera_de_muestra(s, LADO)
            self.fuera_grid[(1, velas)] = fuera
            self.formas.append(Forma(f"SL/TP fijos, cierre {velas} velas", "Salida", velas, dentro, fuera, _texto_combinacion(_mas_elegida(fuera))))
            for nombre, filas in subconjuntos.items():
                sub = s if filas is None else self._semanal(c, m.valores, t, filas)
                f = fuera if filas is None else mt.fuera_de_muestra(sub, LADO)
                filas_p1.append([1, velas, nombre, *_resumen_grid(sub), *_valores_calificacion(f)])

            for z, zona in enumerate(self.zonas):
                filas = c.zona == z
                sub = self._semanal(c, m.valores, None, filas)
                f = mt.fuera_de_muestra(sub, LADO)
                muestra = "Poca muestra" if filas.sum() < config.MUESTRA_MINIMA else ""
                filas_p2.append([zona, int(filas.sum()), muestra, velas, *_resumen_grid(sub), *_valores_calificacion(f)])
            uno = self._politica(c, m.valores, m.salida_ns, np.zeros(len(c), dtype=np.int64))
            por_zona = self._politica(c, m.valores, m.salida_ns, c.zona)
            for nombre, (d, f) in (("Un ATM para todas las zonas", uno), ("Un ATM por cada zona", por_zona)):
                filas_p2.append([f"Política: {nombre}", len(c), "", velas] + [None] * len(_ENC_RESUMEN) + _valores_calificacion(f))
                self.formas.append(Forma(f"{nombre}, cierre {velas} velas", "Elegir ATM", velas, d, f, "", "Elige con datos sin solapamiento"))

            for w, lunes in enumerate(self.semanas):
                filas = c.semana == w
                sub = mt.semanal(m.valores[filas], t[filas], np.zeros(filas.sum(), dtype=np.int64), 1)
                pos = int((sub.total() > 0).sum())
                ops = sub.operaciones.sum(0)
                esperanza = np.divide(sub.total(), ops, out=np.full(LADO * LADO, np.nan), where=ops > 0)
                mejor = int(np.argmax(sub.total()))
                sl, tp = combinacion(mejor)
                filas_p3.append([str(lunes), velas, int(filas.sum()), pos, _r(100 * pos / (LADO * LADO), 1), _r(np.nanmedian(esperanza)), _usd(sl), _usd(tp), _r(sub.total()[mejor])])

            total, ops = s.total(), s.operaciones.sum(0)
            for nombre, mascara in grupos_ratio.items():
                tot = total[mascara]
                esperanza = np.divide(tot, ops[mascara], out=np.full(len(tot), np.nan), where=ops[mascara] > 0)
                mejor = int(np.flatnonzero(mascara)[np.argmax(tot)])
                sl, tp = combinacion(mejor)
                filas_rat.append([velas, nombre, int(mascara.sum()), int((tot > 0).sum()), _r(100 * (tot > 0).mean(), 1), _r(np.nanmedian(esperanza)), _usd(sl), _usd(tp), _r(total[mejor])])

            base_pos, base_fuera = mt.positivas(s)[0], fuera.neto
            filas_p5.append([velas, "Sin breakeven", *_resumen_grid(s), None, *_valores_calificacion(fuera), ""])
            for nivel in config.BREAKEVEN_TICKS:
                mb = matriz(c, velas, "breakeven", nivel)
                tb = self._tomar(c, mb.salida_ns)
                sb = self._semanal(c, mb.valores, tb)
                db, fb = mt.dentro_de_muestra(sb, LADO), mt.fuera_de_muestra(sb, LADO)
                pct_be = _r(100 * np.median((mb.cerrada_be & tb).sum(0) / np.maximum(tb.sum(0), 1)), 1)
                filas_p5.append([velas, f"Breakeven en +{nivel} ticks ({_usd(nivel)} USD)", *_resumen_grid(sb), pct_be, *_valores_calificacion(fb), _veredicto(mt.positivas(sb)[0], base_pos, fb.neto, base_fuera)])
                self.formas.append(Forma(f"Breakeven en +{nivel}, cierre {velas} velas", "Gestión", velas, db, fb, _texto_combinacion(_mas_elegida(fb))))
            ms = matriz(c, velas, "sl_tiempo")
            ts = self._tomar(c, ms.salida_ns)
            ss = self._semanal(c, ms.valores, ts)
            ds, fs = mt.dentro_de_muestra(ss, LADO), mt.fuera_de_muestra(ss, LADO)
            filas_p6.append([velas, "SL fijo", *_resumen_grid(s), *_valores_calificacion(fuera), ""])
            filas_p6.append([velas, "SL que se acerca cada vela", *_resumen_grid(ss), *_valores_calificacion(fs), _veredicto(mt.positivas(ss)[0], base_pos, fs.neto, base_fuera)])
            self.formas.append(Forma(f"SL por tiempo, cierre {velas} velas", "Gestión", velas, ds, fs, _texto_combinacion(_mas_elegida(fs))))

            for familia, funcion in OTRAS_SALIDAS.items():
                valores, salida, nombres = matriz_lista(c, velas, funcion)
                to = self._tomar(c, salida)
                so = self._semanal(c, valores, to)
                do, fo = mt.dentro_de_muestra(so, None), mt.fuera_de_muestra(so, None)
                filas_otras.append([familia, velas, len(nombres), *_valores_calificacion(do), nombres[do.elegidas[0]], *_valores_calificacion(fo), nombres[_mas_elegida(fo)]])
                if familia != "SL/TP fijos (misma cuadrícula gruesa)":
                    self.formas.append(Forma(f"{familia}, cierre {velas} velas", "Salida", velas, do, fo, nombres[_mas_elegida(fo)]))

            if velas == config.VELAS_ENTREGABLES:
                self.k4[1] = (m, t)

        calif = _bloque_calificacion("Fuera")
        self.tablas["P1 Cierre por tiempo"] = Tabla("P1 Cierre por tiempo", ["Escenario", "Velas", "Grupo", *_ENC_RESUMEN, *calif], filas_p1)
        self.tablas["P2 Cierre por zona"] = Tabla("P2 Cierre por zona", ["Zona Reacción", "Señales", "Muestra", "Velas", *_ENC_RESUMEN, *calif], filas_p2)
        self.tablas["P3 Cierre por semana"] = Tabla("P3 Cierre por semana", ["Semana (lunes)", "Velas", "Señales", "Combinaciones positivas", "% positivas", "Mediana de Esperanza (USD)", "Mejor: SL (USD)", "Mejor: TP (USD)", "Mejor: neto (USD)"], filas_p3)
        self.tablas["Ratios"] = Tabla("Ratios", ["Velas", "Ratio TP/SL", "Combinaciones", "Positivas", "% positivas", "Mediana de Esperanza (USD)", "Mejor: SL (USD)", "Mejor: TP (USD)", "Mejor: neto (USD)"], filas_rat)
        self.tablas["P5 Breakeven"] = Tabla("P5 Breakeven", ["Velas", "Gestión", *_ENC_RESUMEN, "% cerradas en breakeven (mediana)", *calif, "¿Mejor que sin breakeven?"], filas_p5)
        self.tablas["P6 SL por tiempo"] = Tabla("P6 SL por tiempo", ["Velas", "Gestión", *_ENC_RESUMEN, *calif, "¿Mejor que SL fijo?"], filas_p6)
        self.tablas["Otras salidas"] = Tabla("Otras salidas", ["Forma", "Velas", "Parámetros probados", *_bloque_calificacion("Dentro"), "Dentro: parámetros", *calif, "Fuera: parámetros más elegidos"], filas_otras)

    # ---- escenarios 2 a 4 ---------------------------------------------------------------------

    def escenarios(self) -> None:
        filas_p1 = self.tablas["P1 Cierre por tiempo"].filas
        filas_p4 = []
        cambios = {2: "Orden a 7 ticks en vez de 3", 3: "Colocar la orden a 700 ms en vez de 300", 4: "Deslizamiento de entrada de 6 ticks en vez de 3"}
        for e in (2, 3, 4):
            c = self.c[e]
            for velas in config.SIM_VELAS:
                self.avisar(f"  Escenario {e}, cierre a {velas} velas...")
                m = matriz(c, velas)
                t = self._tomar(c, m.salida_ns)
                s = self._semanal(c, m.valores, t)
                fuera = mt.fuera_de_muestra(s, LADO)
                self.totales[(e, velas)] = s.total()
                filas_p1.append([e, velas, "Todas", *_resumen_grid(s), *_valores_calificacion(fuera)])
                base, otro = self.totales[(1, velas)], s.total()
                filas_p4.append([
                    velas, f"E1 frente a E{e}", cambios[e], int((base > 0).sum()), int((otro > 0).sum()), int((otro > 0).sum() - (base > 0).sum()),
                    _r(np.median(otro - base)), _r(100 * (base > otro).mean(), 1), _r(self.fuera_grid[(1, velas)].neto), _r(fuera.neto),
                ])
                if velas == config.VELAS_ENTREGABLES:
                    self.k4[e] = (m, t)
        filas_p1.sort(key=lambda f: (f[0], f[1]))
        self.tablas["P4 Escenarios"] = Tabla("P4 Escenarios", [
            "Velas", "Comparación", "Qué cambia", "Positivas E1", "Positivas del otro", "Diferencia de positivas",
            "Mediana de la diferencia de neto por combinación (USD)", "% combinaciones donde gana E1", "Fuera E1: neto (USD)", "Fuera del otro: neto (USD)",
        ], filas_p4)

    # ---- reglas del día -----------------------------------------------------------------------

    def reglas_dia(self) -> None:
        c = self.c[1]
        m, _ = self.k4[1]
        fuera = self.fuera_grid[(1, config.VELAS_ENTREGABLES)]
        elegido = np.array(fuera.elegidas)[c.semana]
        filas = np.arange(len(c))
        v = m.valores[filas, elegido].astype(np.float64)
        s = m.salida_ns[filas, elegido]
        catalogo = reglas(c.minutos, c.zona, self.zonas, config)
        resultados = {}
        for nombre, regla in catalogo.items():
            tomadas = aplicar(v, c.entrada_ns, s, c.dia, regla)
            resultados[nombre] = mt.calificar_operaciones(v[tomadas], c.semana[tomadas], self.nsem)

        # Dejar de operar las zonas que perdieron en las semanas de entrenamiento
        deja = np.ones(len(c), dtype=bool)
        for w in range(self.nsem):
            entreno = c.semana != w
            for z in range(len(self.zonas)):
                g = entreno & (c.zona == z)
                if g.sum() >= config.MUESTRA_MINIMA and v[g].mean() < 0:
                    deja[(c.semana == w) & (c.zona == z)] = False
        tomadas = aplicar(v, c.entrada_ns, s, c.dia, lambda k, e: bool(deja[k]))
        resultados["Dejar de operar las zonas que perdieron en las otras semanas"] = mt.calificar_operaciones(v[tomadas], c.semana[tomadas], self.nsem)

        base = resultados["Base (sin reglas del día)"]
        filas_p7 = []
        for nombre, r in resultados.items():
            mejora = r.neto > base.neto and r.mitad2 > base.mitad2
            filas_p7.append([nombre, *_valores_calificacion(r), _r(r.neto - base.neto), "" if r is base else ("Sí" if mejora else "No")])
            if r is not base:
                self.formas.append(Forma(f"Regla: {nombre}", "Regla del día", config.VELAS_ENTREGABLES, r, r, "ATM fijo elegido fuera de muestra", "Dentro = Fuera: la regla no se elige"))
        self.tablas["P7 Reglas del día"] = Tabla("P7 Reglas del día", ["Regla (cada una por separado)", *_bloque_calificacion("Fuera"), "Diferencia de neto frente a la base (USD)", "¿Añade valor?"], filas_p7)

    # ---- indicadores --------------------------------------------------------------------------

    def indicadores(self, valores_ind: dict[str, np.ndarray], tabla_apertura: list[list]) -> None:
        c = self.c[1]
        m, _ = self.k4[1]
        azar = np.random.default_rng(config.AZAR_SEMILLA)

        mfe, mae_pre = [], []
        for op in c.ops:
            f = op.favor[:op.cierre(config.VELAS_ENTREGABLES)]
            i = int(np.argmax(f))
            mfe.append(float(f[i]))
            mae_pre.append(float(-f[:i + 1].min()))
        mfe, mae_pre = np.array(mfe), np.array(mae_pre)
        apertura = c.minutos < config.VELAS_APERTURA * c.te
        dias = np.unique(c.dia)

        def por_dia(x: np.ndarray) -> np.ndarray:
            return np.array([np.nanmedian(x[c.dia == d]) if np.any(~np.isnan(x[c.dia == d])) else np.nan for d in dias])

        filas_rel = []
        for nombre, x in valores_ind.items():
            filas_rel.append([
                nombre, int((~np.isnan(x)).sum()), spearman(x, mfe), spearman(x, mae_pre), spearman(por_dia(x), por_dia(mfe)), spearman(por_dia(x), por_dia(mae_pre)),
                spearman(x[apertura], mfe[apertura]), spearman(x[~apertura], mfe[~apertura]),
            ])
        self.tablas["Por qué cambian los días"] = Tabla("Por qué cambian los días", [
            "Indicador", "Señales con valor", "Relación con MFE (por señal)", "Relación con MAE pre MFE (por señal)",
            "Relación con MFE (por día)", "Relación con MAE pre MFE (por día)", "MFE: señales de las primeras 10 velas", "MFE: resto de señales",
        ], filas_rel)

        filas_tramos, filas_fuera = [], []
        uno = self._politica(c, m.valores, m.salida_ns, np.zeros(len(c), dtype=np.int64))
        falsos = []
        for _ in range(config.AGRUPACIONES_FALSAS):
            etiquetas = azar.integers(0, 3, len(self.dias))[c.dia]
            falsos.append(self._politica(c, m.valores, m.salida_ns, etiquetas)[1].neto)
        falsos = np.array(falsos)
        global_ = mt.elegir(m.valores.sum(0, dtype=np.float64), LADO)
        for nombre, x in valores_ind.items():
            cortes = np.nanquantile(x, [1 / 3, 2 / 3])
            etiquetas = np.where(np.isnan(x), -1, np.digitize(x, cortes))
            limites = [(-np.inf, cortes[0]), (cortes[0], cortes[1]), (cortes[1], np.inf)]
            for g, (a, b) in enumerate(limites):
                filas = etiquetas == g
                if filas.sum() == 0:
                    continue
                suma = m.valores[filas].sum(0, dtype=np.float64)
                mejor = mt.elegir(suma, LADO)
                sl, tp = combinacion(mejor)
                filas_tramos.append([
                    nombre, ["Bajo", "Medio", "Alto"][g], _r(a) if np.isfinite(a) else None, _r(b) if np.isfinite(b) else None, int(filas.sum()),
                    _usd(sl), _usd(tp), _r(suma[mejor] / filas.sum()), _r(suma[global_] / filas.sum()),
                ])

            def tercios(entreno: np.ndarray, x=x) -> np.ndarray:
                ok = entreno & ~np.isnan(x)
                q = np.nanquantile(x[ok], [1 / 3, 2 / 3])
                return np.where(np.isnan(x), -1, np.digitize(x, q))

            d, f = self._politica(c, m.valores, m.salida_ns, tercios)
            percentil = _r(100 * (falsos < f.neto).mean(), 0)
            sirve = "Sí" if f.neto > uno[1].neto and percentil >= 95 else "No"
            filas_fuera.append([nombre, *_valores_calificacion(d)[:2], *_valores_calificacion(f), _r(uno[1].neto), percentil, sirve])
            self.formas.append(Forma(f"ATM por tramo de {nombre}", "Elegir ATM", config.VELAS_ENTREGABLES, d, f, "", f"Percentil contra tramos falsos: {percentil}"))
        self.tablas["P3 Indicadores tramos"] = Tabla("P3 Indicadores tramos", [
            "Indicador", "Tramo", "Desde", "Hasta", "Señales", "Mejor zona: SL (USD)", "Mejor zona: TP (USD)",
            "Esperanza de esa zona en el tramo (USD)", "Esperanza del ATM general en el tramo (USD)",
        ], filas_tramos)
        self.tablas["P3 Indicadores fuera"] = Tabla("P3 Indicadores fuera", [
            "Indicador", "Dentro: neto (USD)", "Dentro: PF", *_bloque_calificacion("Fuera"),
            "Fuera con un solo ATM (USD)", "Percentil contra tramos falsos", "¿Sirve para elegir el ATM?",
        ], filas_fuera)
        self.tablas["P3 ATR en la apertura"] = Tabla("P3 ATR en la apertura", [
            "Vela desde la apertura (1 min)", "Días", "ATR(5) / ATR NY (mediana)", "ATR(10) / ATR NY (mediana)",
            "% días con ATR(5) a ±20 % del ATR NY", "% días con ATR(10) a ±20 % del ATR NY",
        ], tabla_apertura)
        self.falsos_indicador = falsos

    # ---- validación -----------------------------------------------------------------------------

    def validacion(self, calendario) -> None:
        c = self.c[1]
        velas = config.VELAS_ENTREGABLES
        azar = np.random.default_rng(config.AZAR_SEMILLA)
        escenario = config.ESCENARIOS[0]
        fuera_azar = []
        for i in range(config.AZAR_CARTERAS):
            if i % 20 == 0:
                self.avisar(f"  Carteras al azar {i}/{config.AZAR_CARTERAS}...")
            ca = conjunto(al_azar(c, self.dias, azar, escenario[2], escenario[3]), self.dias, calendario)
            ma = matriz(ca, velas)
            sa = mt.semanal(ma.valores, mt.tomar_sin_solape(ca.entrada_ns, ma.salida_ns), ca.semana, self.nsem)
            fuera_azar.append(mt.fuera_de_muestra(sa, LADO).neto)
        self.fuera_azar = np.array(fuera_azar)
        ci = conjunto(inversas(c, self.dias, escenario[3]), self.dias, calendario)
        mi = matriz(ci, velas)
        si = mt.semanal(mi.valores, mt.tomar_sin_solape(ci.entrada_ns, mi.salida_ns), ci.semana, self.nsem)
        inversa = mt.fuera_de_muestra(si, LADO)
        propia = self.fuera_grid[(1, velas)]

        m, _ = self.k4[1]
        falsos_zona = []
        for _ in range(config.AGRUPACIONES_FALSAS):
            permutada = azar.permutation(c.zona)
            falsos_zona.append(self._politica(c, m.valores, m.salida_ns, permutada)[1].neto)
        falsos_zona = np.array(falsos_zona)
        por_zona = self._politica(c, m.valores, m.salida_ns, c.zona)[1].neto

        p = lambda x: np.percentile(x, [5, 50, 95])
        filas = [
            ["Tus señales frente a 100 carteras al azar (mismo minuto de otro día, dirección al azar)", f"SL/TP fijos, {velas} velas", _r(propia.neto), *[_r(v) for v in p(self.fuera_azar)], _r(100 * (self.fuera_azar < propia.neto).mean(), 0)],
            ["Tus señales frente a la operación inversa (mismo instante, dirección contraria)", f"SL/TP fijos, {velas} velas", _r(propia.neto), _r(inversa.neto), None, None, None],
            ["ATM por zona frente a 100 agrupaciones falsas de zonas", f"{velas} velas", _r(por_zona), *[_r(v) for v in p(falsos_zona)], _r(100 * (falsos_zona < por_zona).mean(), 0)],
            ["Tramos de indicador frente a 100 tramos falsos por día", f"{velas} velas", None, *[_r(v) for v in p(self.falsos_indicador)], None],
        ]
        for v in config.SIM_VELAS:
            filas.append([f"Probabilidad de sobreajuste (PBO) de elegir la mejor combinación", f"SL/TP fijos, {v} velas", _r(100 * mt.pbo(self.semanal_e1[v]), 1), None, None, None, None])
        self.tablas["Validación"] = Tabla("Validación", ["Prueba", "Forma", "Resultado fuera (USD) o PBO (%)", "Referencia p5", "Referencia p50", "Referencia p95", "Percentil de tu resultado"], filas)

    # ---- recomendación ----------------------------------------------------------------------------

    def recomendacion(self) -> None:
        filas = []
        for f in sorted(self.formas, key=lambda x: -x.fuera.neto):
            percentil = _r(100 * (self.fuera_azar < f.fuera.neto).mean(), 0)
            candidata = f.fuera.neto > 0 and f.fuera.mitad1 > 0 and f.fuera.mitad2 > 0
            nivel = "Confirmada" if candidata and percentil >= 95 else ("Candidata" if candidata else "No")
            filas.append([f.nombre, f.tipo, f.velas, *_valores_calificacion(f.dentro)[:2], *_valores_calificacion(f.fuera), percentil, nivel, f.combinacion, f.nota])
        self.tablas["P8 Recomendación"] = Tabla("P8 Recomendación", [
            "Forma de operar", "Tipo", "Velas", "Dentro: neto (USD)", "Dentro: PF", *_bloque_calificacion("Fuera"),
            "Percentil contra carteras al azar", "Nivel", "Combinación más elegida", "Nota",
        ], filas)


def _veredicto(pos: int, pos_base: int, fuera: float, fuera_base: float) -> str:
    mas = pos > pos_base
    mejor = fuera > fuera_base
    texto = f"{'más' if mas else 'menos'} combinaciones positivas ({pos} frente a {pos_base}) y {'mejor' if mejor else 'peor'} fuera de muestra ({fuera:+.0f} frente a {fuera_base:+.0f} USD)"
    if mas and mejor:
        return "Sí: " + texto
    if not mas and not mejor:
        return "No: " + texto
    return "Depende: " + texto
