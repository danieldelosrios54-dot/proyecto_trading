"""Tablas de analisis_mfe_mae.xlsx. Cada función produce una pestaña."""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

import config
from medicion.azar import medir_azar
from medicion.entrada import Dia, Escenario, signo_de
from medicion.recorrido import Recorrido, tras_ir_a_favor
from validacion.modelos import Senal, clave_fecha

_H = list(config.HORIZONTES)
_MEDIDAS = ("mfe", "mae_pre_mfe", "mae")


@dataclass
class Medicion:
    senal: Senal
    revision: str
    precio_op: int | None = None
    ejecucion: str | None = None
    indice: int | None = None
    hora_entrada_ns: int | None = None
    precio_entrada: int | None = None
    tiempo_ns: int | None = None
    tramos: dict[int, Recorrido] | None = None


@dataclass(frozen=True)
class Contexto:
    atr_senal: float | None
    atr_dia_anterior: float | None
    volumen_dia_anterior: int | None


@dataclass(frozen=True)
class Tabla:
    titulo: str
    encabezados: list[str]
    filas: list[list]


@dataclass
class Matriz:
    escenario: Escenario
    mediciones: list[Medicion]
    ejecutadas: list[Medicion]
    mfe: np.ndarray
    mae_pre_mfe: np.ndarray
    mae: np.ndarray
    segundos_mfe: np.ndarray
    claves: np.ndarray
    semanas: list[date]
    atr: np.ndarray


def crear_matriz(escenario: Escenario, mediciones: list[Medicion], contexto: dict[int, Contexto]) -> Matriz:
    ej = [m for m in mediciones if m.ejecucion == config.EJECUTADA]
    columna = lambda campo: np.array([[getattr(m.tramos[x], campo) for x in _H] for m in ej], dtype=float).reshape(len(ej), len(_H))
    segundos = np.array([[(m.tramos[x].hora_mfe_ns - m.hora_entrada_ns) / 1e9 for x in _H] for m in ej], dtype=float).reshape(len(ej), len(_H))
    return Matriz(
        escenario, mediciones, ej, columna("mfe"), columna("mae_pre_mfe"), columna("mae"), segundos,
        np.array([clave_fecha(m.senal.fecha) for m in ej]),
        [m.senal.fecha - timedelta(days=m.senal.fecha.weekday()) for m in ej],
        np.array([np.nan if contexto[m.senal.fila].atr_senal is None else contexto[m.senal.fila].atr_senal for m in ej], dtype=float),
    )


def al_menos(valores: np.ndarray, porcentaje: float) -> float:
    """Valor al que llegó al menos ese % de las señales."""
    return float(np.sort(valores)[::-1][math.ceil(porcentaje / 100 * len(valores)) - 1])


def no_paso_de(valores: np.ndarray, porcentaje: float) -> float:
    """Valor del que no pasó ese % de las señales."""
    return float(np.sort(valores)[math.ceil(porcentaje / 100 * len(valores)) - 1])


def clasificar(mfe: np.ndarray, mae_pre_mfe: np.ndarray, mae: np.ndarray, sl: int, tp: int) -> tuple[int, int, int, int, int]:
    """(Positivas, Negativas, Negativas tras el máximo, Sin tocar, Dudosas)."""
    tp_si = mfe >= tp
    sl_pre = mae_pre_mfe >= sl
    resto = ~sl_pre & ~tp_si
    return (
        int((~sl_pre & tp_si).sum()),
        int((sl_pre & ~tp_si).sum()),
        int((resto & (mae >= sl)).sum()),
        int((resto & (mae < sl)).sum()),
        int((sl_pre & tp_si).sum()),
    )


def _i(minutos: int) -> int:
    return _H.index(minutos)


def _mediana(a: np.ndarray) -> float | None:
    return float(np.median(a)) if a.size else None


def _pct(a: np.ndarray, p: float) -> float | None:
    return round(float(np.quantile(a, p / 100)), 1) if a.size else None


def _margen(valores: np.ndarray, dias: np.ndarray, azar: np.random.Generator) -> tuple[float | None, float | None]:
    """Margen del 95 % de la mediana, remuestreando días completos."""
    unicos = np.unique(dias)
    if unicos.size < 2:
        return None, None
    grupos = [valores[dias == d] for d in unicos]
    medianas = [
        np.median(np.concatenate([grupos[j] for j in azar.integers(0, len(grupos), len(grupos))]))
        for _ in range(config.BOOTSTRAP_REPETICIONES)
    ]
    return round(float(np.quantile(medianas, 0.025)), 1), round(float(np.quantile(medianas, 0.975)), 1)


def resumen(matrices: list[Matriz]) -> Tabla:
    filas = []
    for m in matrices:
        rev = Counter(x.revision for x in m.mediciones)
        eje = Counter(x.ejecucion for x in m.mediciones)
        filas.append([
            m.escenario.numero, len(m.mediciones), rev[config.REVISION_VALIDA],
            rev[config.REVISION_INVALIDA_R], rev[config.REVISION_INVALIDA_T], rev[config.REVISION_INVALIDA_OP],
            eje[config.EJECUTADA], eje[config.NO_EJECUTADA], eje[config.NO_EJECUTADA_OP],
        ])
    return Tabla("Resumen", ["Escenario", "Registradas", "Validas", "Invalida R", "Invalida T", "Invalida OP", "Ejecutadas", "No Ejecutadas", "No Ejecutadas OP"], filas)


def recorridos_tabla(matrices: list[Matriz], dias: dict[str, Dia]) -> Tabla:
    filas = []
    for m in matrices:
        referencia = [(clave_fecha(x.senal.fecha), x.hora_entrada_ns - dias[clave_fecha(x.senal.fecha)].apertura_ns) for x in m.ejecutadas]
        azar = medir_azar(referencia, dias, m.escenario.deslizamiento)
        for minutos in _H:
            i = _i(minutos)
            for p in config.PORCENTAJES_SENALES:
                filas.append([
                    m.escenario.numero, minutos, p,
                    al_menos(m.mfe[:, i], p), no_paso_de(m.mae_pre_mfe[:, i], p), no_paso_de(m.mae[:, i], p),
                    al_menos(azar["mfe"][:, i], p), no_paso_de(azar["mae_pre_mfe"][:, i], p), no_paso_de(azar["mae"][:, i], p),
                ])
    return Tabla("Recorridos", ["Escenario", "Minutos", "% de señales", "MFE: llegó al menos a", "MAE pre MFE: no pasó de", "MAE: no pasó de", "Azar MFE", "Azar MAE pre MFE", "Azar MAE"], filas)


def combinaciones(matrices: list[Matriz]) -> Tabla:
    filas = []
    for m in matrices:
        for minutos in _H:
            i = _i(minutos)
            for sl in config.CUADRICULA_SL_TP:
                for tp in config.CUADRICULA_SL_TP:
                    filas.append([m.escenario.numero, minutos, sl, tp, sl * config.USD_POR_TICK, tp * config.USD_POR_TICK, len(m.ejecutadas), *clasificar(m.mfe[:, i], m.mae_pre_mfe[:, i], m.mae[:, i], sl, tp)])
    return Tabla("Combinaciones", ["Escenario", "Minutos", "SL (ticks)", "TP (ticks)", "SL (USD)", "TP (USD)", "Señales ejecutadas", "Positivas", "Negativas", "Negativas tras el máximo", "Sin tocar", "Dudosas"], filas)


def ventana_tiempo(matrices: list[Matriz]) -> Tabla:
    filas = []
    for m in matrices:
        ultimo = m.mfe[:, -1]
        for minutos in _H:
            i = _i(minutos)
            filas.append([
                m.escenario.numero, minutos, _mediana(m.mfe[:, i]), _mediana(m.mae_pre_mfe[:, i]), _mediana(m.mae[:, i]), round(_mediana(m.segundos_mfe[:, i]), 1),
                round(100 * float((m.mfe[:, i] == ultimo).mean()), 1), round(100 * float((m.mae[:, i] > m.mae_pre_mfe[:, i]).mean()), 1),
            ])
    return Tabla("Ventana de tiempo", ["Escenario", "Minutos", "MFE mediana", "MAE pre MFE mediana", "MAE mediana", "Segundos hasta MFE (mediana)", "% con MFE igual al de 10 min", "% con MAE mayor que MAE pre MFE"], filas)


def escenarios_comparados(matrices: list[Matriz]) -> Tabla:
    base = matrices[0]
    filas_base = {x.senal.fila: k for k, x in enumerate(base.ejecutadas)}
    filas = []
    for otro in matrices[1:3]:
        filas_otro = {x.senal.fila: k for k, x in enumerate(otro.ejecutadas)}
        comunes = sorted(set(filas_base) & set(filas_otro))
        ib, io = [filas_base[f] for f in comunes], [filas_otro[f] for f in comunes]
        for minutos in _H:
            i = _i(minutos)
            filas.append([
                f"E1 vs E{otro.escenario.numero}", minutos, len(comunes), len(set(filas_base) - set(filas_otro)), len(set(filas_otro) - set(filas_base)),
                *[round(_mediana(getattr(otro, c)[io, i]) - _mediana(getattr(base, c)[ib, i]), 1) for c in _MEDIDAS],
            ])
    return Tabla("Escenarios", ["Comparación", "Minutos", "Señales en ambos", "Solo en E1", "Solo en el otro", "Diferencia MFE (mediana)", "Diferencia MAE pre MFE (mediana)", "Diferencia MAE (mediana)"], filas)


def semanas(m: Matriz, atr_dia: dict[str, float], volumen_dia: dict[str, int]) -> Tabla:
    azar = np.random.default_rng(config.BOOTSTRAP_SEMILLA)
    lunes = np.array(m.semanas)
    filas = []
    for semana in sorted(set(m.semanas)):
        mascara = lunes == semana
        claves_semana = sorted(set(m.claves[mascara]))
        atr = round(float(np.mean([atr_dia[c] for c in claves_semana if atr_dia[c] is not None])), 1)
        volumen = round(float(np.mean([volumen_dia[c] for c in claves_semana])))
        for minutos in _H:
            i = _i(minutos)
            fila = [semana.isoformat(), minutos, int(mascara.sum()), atr, volumen]
            for campo in _MEDIDAS:
                valores = getattr(m, campo)[mascara, i]
                fila += [_mediana(valores), *_margen(valores, m.claves[mascara], azar)]
            filas.append(fila)
    return Tabla("Semanas", ["Semana (lunes)", "Minutos", "Señales", "ATR NY (promedio)", "Volumen 1ª hora (promedio)", "MFE mediana", "MFE margen bajo", "MFE margen alto", "MAE pre MFE mediana", "MAE pre margen bajo", "MAE pre margen alto", "MAE mediana", "MAE margen bajo", "MAE margen alto"], filas)


def por_grupo(m: Matriz) -> Tabla:
    grupos = [("Zona Reacción", z, np.array([x.senal.zona == z for x in m.ejecutadas])) for z in sorted(config.ZONAS)]
    grupos += [("Tipo", t, np.array([x.senal.tipo == t for x in m.ejecutadas])) for t in sorted(config.VALORES_TIPO)]
    grupos += [("Te", te, np.array([x.senal.te == te for x in m.ejecutadas])) for te in sorted(config.VALORES_TE)]
    filas = []
    for columna, valor, mascara in grupos:
        n = int(mascara.sum())
        if n == 0:
            continue
        marca = "Poca muestra" if n < config.MUESTRA_MINIMA else ""
        for minutos in _H:
            i = _i(minutos)
            mfe, pre, mae = m.mfe[mascara, i], m.mae_pre_mfe[mascara, i], m.mae[mascara, i]
            filas.append([
                columna, valor, minutos, n, marca,
                al_menos(mfe, 50), al_menos(mfe, 67), al_menos(mfe, 90),
                no_paso_de(pre, 50), no_paso_de(pre, 67), no_paso_de(pre, 90),
                no_paso_de(mae, 50), no_paso_de(mae, 67), no_paso_de(mae, 90),
            ])
    return Tabla("Por grupo", ["Columna", "Valor", "Minutos", "Señales", "Muestra", "MFE 50 %", "MFE 67 %", "MFE 90 %", "MAE pre MFE 50 %", "MAE pre MFE 67 %", "MAE pre MFE 90 %", "MAE 50 %", "MAE 67 %", "MAE 90 %"], filas)


def mae_pre_por_mfe(m: Matriz) -> Tabla:
    filas = []
    for minutos in _H:
        i = _i(minutos)
        mfe, pre = m.mfe[:, i], m.mae_pre_mfe[:, i]
        filas.append([minutos, "Todas", len(mfe), _pct(pre, 50), _pct(pre, 67), _pct(pre, 90)])
        for bajo, alto in config.NIVELES_MFE:
            mascara = np.ones(len(mfe), dtype=bool)
            if bajo is not None:
                mascara &= mfe >= bajo
            if alto is not None:
                mascara &= mfe < alto
            nombre = f"Menos de {alto}" if bajo is None else (f"{bajo} o más" if alto is None else f"{bajo} a {alto}")
            sel = pre[mascara]
            filas.append([minutos, nombre, int(mascara.sum()), _pct(sel, 50), _pct(sel, 67), _pct(sel, 90)])
    return Tabla("MAE pre por MFE", ["Minutos", "MFE alcanzado", "Señales", "MAE pre MFE p50", "MAE pre MFE p67", "MAE pre MFE p90"], filas)


def rangos_atr(m: Matriz, contexto: dict[int, Contexto], fechas_ordenadas: list[str], atr_dia: dict[str, float]) -> Tabla:
    previos = [atr_dia[f] for f in fechas_ordenadas[:-1] if atr_dia[f] is not None]
    corte_bajo, corte_alto = (float(q) for q in np.quantile(previos, [1 / 3, 2 / 3]))
    atr = np.array([np.nan if contexto[x.senal.fila].atr_dia_anterior is None else contexto[x.senal.fila].atr_dia_anterior for x in m.ejecutadas], dtype=float)
    rangos = (
        ("Bajo", None, corte_bajo, atr <= corte_bajo),
        ("Medio", corte_bajo, corte_alto, (atr > corte_bajo) & (atr <= corte_alto)),
        ("Alto", corte_alto, None, atr > corte_alto),
    )
    filas = []
    for minutos in _H:
        i = _i(minutos)
        for nombre, desde, hasta, mascara in rangos:
            filas.append([
                minutos, nombre, None if desde is None else round(desde, 1), None if hasta is None else round(hasta, 1), int(mascara.sum()),
                _pct(m.mfe[mascara, i], 50), _pct(m.mfe[mascara, i], 75), _pct(m.mae_pre_mfe[mascara, i], 50), _pct(m.mae_pre_mfe[mascara, i], 90), _pct(m.mae[mascara, i], 50), _pct(m.mae[mascara, i], 90),
            ])
    return Tabla("Rangos ATR NY", ["Minutos", "Rango ATR NY día anterior", "Desde (ticks)", "Hasta (ticks)", "Señales", "MFE p50", "MFE p75", "MAE pre MFE p50", "MAE pre MFE p90", "MAE p50", "MAE p90"], filas)


def proporcion(m: Matriz) -> Tabla:
    semanas_orden = sorted(set(m.semanas))
    primera = set(semanas_orden[: len(semanas_orden) // 2])
    es_primera = np.array([s in primera for s in m.semanas])
    filas = []
    for minutos in _H:
        i = _i(minutos)
        lecturas = []
        for nombre, mascara in (("Mitad 1", es_primera), ("Mitad 2", ~es_primera)):
            valores = [_mediana(getattr(m, c)[mascara, i]) for c in _MEDIDAS]
            prop = [_mediana(getattr(m, c)[mascara, i] / m.atr[mascara]) for c in _MEDIDAS]
            lecturas.append(valores + prop)
            filas.append([minutos, nombre, int(mascara.sum()), *valores, *[round(p, 3) for p in prop]])
        filas.append([minutos, "Cambio %", None, *[round(100 * (b / a - 1), 1) if a else None for a, b in zip(lecturas[0], lecturas[1])]])
    return Tabla("Proporción", ["Minutos", "Mitad de la muestra", "Señales", "MFE (ticks)", "MAE pre MFE (ticks)", "MAE (ticks)", "MFE / ATR NY", "MAE pre MFE / ATR NY", "MAE / ATR NY"], filas)


def despues_a_favor(m: Matriz, dias: dict[str, Dia]) -> Tabla:
    filas = []
    for nivel in config.NIVELES_A_FAVOR:
        resultados = [
            tras_ir_a_favor(dias[clave_fecha(x.senal.fecha)], x.indice, x.precio_entrada, signo_de(x.senal), nivel)
            for x in m.ejecutadas
        ]
        llegan = [r for r in resultados if r.llega]
        vuelven = sum(r.vuelve_a_entrada for r in llegan)
        sin_volver = [r.maximo for r in llegan if not r.vuelve_a_entrada]
        filas.append([
            nivel, len(llegan), round(100 * len(llegan) / len(resultados), 1), vuelven,
            round(100 * vuelven / len(llegan), 1) if llegan else None, float(np.median(sin_volver)) if sin_volver else None,
        ])
    return Tabla("Después de ir a favor", ["Nivel a favor (ticks)", "Señales que llegan", "% que llega", "Vuelven a la entrada", "% que vuelve (de las que llegan)", "MFE mediana de las que no vuelven"], filas)


def construir_analisis(matrices: list[Matriz], dias: dict[str, Dia], contexto: dict[int, Contexto], atr_dia: dict[str, float], volumen_dia: dict[str, int]) -> list[Tabla]:
    principal = matrices[0]
    return [
        resumen(matrices),
        recorridos_tabla(matrices, dias),
        combinaciones(matrices),
        ventana_tiempo(matrices),
        escenarios_comparados(matrices),
        semanas(principal, atr_dia, volumen_dia),
        por_grupo(principal),
        mae_pre_por_mfe(principal),
        rangos_atr(principal, contexto, sorted(dias), atr_dia),
        proporcion(principal),
        despues_a_favor(principal, dias),
    ]
