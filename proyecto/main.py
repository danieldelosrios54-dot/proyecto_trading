"""Punto de entrada del proyecto. Uso: python main.py validar | medir | simular | principal"""

import sys
import time
from collections import Counter
from dataclasses import dataclass

import polars as pl

import config
from medicion.analisis import Contexto, Matriz, Medicion, construir_analisis, crear_matriz
from medicion.entrada import ESCENARIOS, Dia, Escenario, cargar_dia, orden_valida, precio_base_y_cierre, precio_orden, signo_de, simular_entrada
from medicion.recorrido import recorridos
from medicion.reportes import escribir_analisis, escribir_resultados
from medicion.volatilidad import atr_apertura, atr_hasta, volumen_primera_hora
from validacion.extraccion import Ventana, extraer, fecha_de_clave, hms, ruta_parquet
from validacion.modelos import Motivo, Senal, clave_fecha, estado, ns_del_dia
from validacion.registro import leer_registro, validar_registro
from validacion.reportes import reporte_senales, reporte_ticks
from validacion.ticks import (
    ResultadoFecha,
    aplicar_t12,
    en_tramo,
    estado_fecha,
    motivos_senal,
    tramo_ns,
    validar_dia,
)
from validacion.velas import regla_r13


@dataclass
class Validacion:
    senales: list[Senal]
    motivos_r: dict[int, list[Motivo]]
    motivos_t: dict[int, list[Motivo]]
    aperturas: dict[str, int]  # segundos UTC por fecha


def _ventanas_por_fecha(senales: list[Senal]) -> dict[str, tuple[int, Ventana]]:
    """Ventana a extraer de cada fecha, a partir de su "Apertura UTC"."""
    aperturas: dict[str, Counter] = {}
    for s in senales:
        if s.fecha is not None and s.apertura_s in config.APERTURAS_UTC_S:
            aperturas.setdefault(clave_fecha(s.fecha), Counter())[s.apertura_s] += 1
    ventanas = {}
    for clave, conteo in aperturas.items():
        apertura = conteo.most_common(1)[0][0]
        ventanas[clave] = (apertura, Ventana(
            hms(apertura - config.MINUTOS_ANTES_APERTURA * 60),
            hms(apertura + config.MINUTOS_DESPUES_APERTURA * 60),
        ))
    return ventanas


def _motivos_t1_t2_t3(clave: str, archivos: dict) -> list[Motivo]:
    motivos = []
    con_ticks = [n for n, e in archivos.items() if clave in e["fechas_extraidas"]]
    for nombre, entrada in archivos.items():
        t1 = entrada["t1"]
        lineas = t1["en_ventana"].get(clave, 0) + t1["sin_hora"].get(clave, 0)
        if clave in entrada["fechas_archivo"]:
            lineas += t1["sin_fecha"]
        if lineas:
            motivos.append(Motivo("T1", config.INVALIDAR, f"{lineas} línea(s) con formato incorrecto en {nombre}"))
    if not con_ticks:
        motivos.append(Motivo("T2", config.INVALIDAR, "la fecha no está en ningún archivo o su ventana no tiene ticks"))
    if len(con_ticks) > 1:
        motivos.append(Motivo("T3", config.INVALIDAR, f"la ventana tiene ticks en más de un archivo: {', '.join(con_ticks)}"))
    return motivos


def _ejecutar_validacion() -> Validacion | None:
    print("1/5 Leyendo y validando el registro de señales...")
    senales, cond_e, cond_c = leer_registro(config.ARCHIVO_REGISTRO)
    motivos_r = validar_registro(senales, cond_e, cond_c)

    print("2/5 Extrayendo ticks (solo lo nuevo o lo que cambió)...")
    ventanas = _ventanas_por_fecha(senales)
    registro, procesados = extraer(
        config.CARPETA_DATA_TICKS, config.CARPETA_TICKS_EXTRAIDOS, {c: v for c, (_, v) in ventanas.items()}
    )
    print(f"    Archivos procesados: {len(procesados)}")

    print("3/5 Validando ticks y velas por fecha...")
    por_fecha: dict[str, list[Senal]] = {}
    for s in senales:
        if s.fecha is not None:
            por_fecha.setdefault(clave_fecha(s.fecha), []).append(s)

    archivos = registro["archivos"]
    resultados: dict[str, ResultadoFecha] = {}
    for clave in sorted(ventanas):
        resultado = ResultadoFecha(clave, fecha_de_clave(clave))
        resultado.motivos = _motivos_t1_t2_t3(clave, archivos)
        resultados[clave] = resultado
        if not any(clave in e["fechas_extraidas"] for e in archivos.values()):
            continue
        ticks = pl.read_parquet(ruta_parquet(config.CARPETA_TICKS_EXTRAIDOS, clave))
        apertura, _ = ventanas[clave]
        validar_dia(
            resultado, ticks,
            ns_del_dia(resultado.fecha, apertura - config.MINUTOS_ANTES_APERTURA * 60),
            ns_del_dia(resultado.fecha, apertura + config.MINUTOS_DESPUES_APERTURA * 60),
        )
        if estado_fecha(resultado) != config.INVALIDA:
            for s in por_fecha.get(clave, []):
                motivos_r[s.fila] = motivos_r[s.fila] + regla_r13(s, ticks)

    print("4/5 Asignando el estado de cada señal...")
    mediana = aplicar_t12(resultados)
    motivos_t = {
        s.fila: motivos_senal(s, resultados.get(clave_fecha(s.fecha)) if s.fecha else None)
        for s in senales
    }
    senales_por_incidente: Counter = Counter()
    for s in senales:
        if s.fecha is None:
            continue
        resultado = resultados.get(clave_fecha(s.fecha))
        tramo = tramo_ns(s)
        for incidente in resultado.incidentes if resultado else []:
            if en_tramo(incidente, tramo):
                senales_por_incidente[(incidente.regla, incidente.inicio_ns)] += 1

    print("5/5 Escribiendo reportes...")
    reporte_senales(config.REPORTE_SENALES, senales, motivos_r)
    reporte_ticks(config.REPORTE_TICKS, senales, motivos_t, resultados, mediana, senales_por_incidente)

    conteo_r = Counter(estado(motivos_r[s.fila]) for s in senales)
    conteo_t = Counter(estado(motivos_t[s.fila]) for s in senales)
    conteo_f = Counter(estado_fecha(r) for r in resultados.values())
    print(f"Señales ({len(senales)}), registro: {dict(conteo_r)}")
    print(f"Señales ({len(senales)}), ticks:    {dict(conteo_t)}")
    print(f"Fechas ({len(resultados)}):           {dict(conteo_f)}")
    print(f"Reportes en: {config.CARPETA_VALIDACIONES}")
    return Validacion(senales, motivos_r, motivos_t, {c: a for c, (a, _) in ventanas.items()})


def _medir_senal(s: Senal, base_cierre: tuple[int, int] | None, validacion: Validacion, dias: dict[str, Dia], escenario: Escenario) -> Medicion:
    if estado(validacion.motivos_r[s.fila]) == config.INVALIDA:
        return Medicion(s, config.REVISION_INVALIDA_R)
    if estado(validacion.motivos_t[s.fila]) == config.INVALIDA or base_cierre is None:
        return Medicion(s, config.REVISION_INVALIDA_T)
    base, cierre = base_cierre
    signo = signo_de(s)
    precio_op = precio_orden(base, signo, escenario)
    if not orden_valida(precio_op, cierre, signo):
        return Medicion(s, config.REVISION_INVALIDA_OP)
    dia = dias[clave_fecha(s.fecha)]
    entrada = simular_entrada(s, dia, precio_op, escenario)
    if entrada.indice is None:
        return Medicion(s, config.REVISION_VALIDA, precio_op, entrada.estado)
    hora_entrada = int(dia.ns[entrada.indice])
    precio_entrada = precio_op + signo * escenario.deslizamiento
    return Medicion(
        s, config.REVISION_VALIDA, precio_op, entrada.estado, entrada.indice, hora_entrada, precio_entrada,
        hora_entrada - ns_del_dia(s.fecha, s.hora_utc_s), recorridos(dia, entrada.indice, precio_entrada, signo),
    )


@dataclass
class Preparacion:
    validacion: Validacion
    dias: dict[str, Dia]
    contexto: dict[int, Contexto]
    por_escenario: dict[int, list[Medicion]]
    atr_dia: dict[str, float | None]
    volumen_dia: dict[str, int]


def _preparar(escenarios=ESCENARIOS) -> Preparacion:
    """Valida, carga los ticks y simula la entrada de cada señal en cada escenario."""
    validacion = _ejecutar_validacion()

    print("\nCargando ticks extraídos...")
    dias: dict[str, Dia] = {}
    for clave, apertura in sorted(validacion.aperturas.items()):
        ruta = ruta_parquet(config.CARPETA_TICKS_EXTRAIDOS, clave)
        if ruta.exists():
            dias[clave] = cargar_dia(ruta, ns_del_dia(fecha_de_clave(clave), apertura))

    fechas = sorted(dias)
    atr_dia = {c: atr_apertura(dias[c]) for c in fechas}
    volumen_dia = {c: volumen_primera_hora(dias[c]) for c in fechas}
    anterior = {c: fechas[i - 1] if i else None for i, c in enumerate(fechas)}

    contexto: dict[int, Contexto] = {}
    bases: dict[int, tuple[int, int] | None] = {}
    for s in validacion.senales:
        clave = clave_fecha(s.fecha) if s.fecha else None
        apta = clave in dias and s.hora_utc_s is not None and s.vela_op_utc_s is not None and s.te in config.VALORES_TE and s.ohlc in config.VALORES_OHLC
        bases[s.fila] = precio_base_y_cierre(s, dias[clave]) if apta else None
        previo = anterior.get(clave)
        contexto[s.fila] = Contexto(
            atr_hasta(dias[clave], ns_del_dia(s.fecha, s.hora_utc_s)) if apta else None,
            atr_dia[previo] if previo else None,
            volumen_dia[previo] if previo else None,
        )

    por_escenario: dict[int, list[Medicion]] = {}
    for escenario in escenarios:
        print(f"Entradas del Escenario {escenario.numero}...")
        por_escenario[escenario.numero] = [_medir_senal(s, bases[s.fila], validacion, dias, escenario) for s in validacion.senales]
    return Preparacion(validacion, dias, contexto, por_escenario, atr_dia, volumen_dia)


def medir() -> int:
    inicio = time.time()
    try:
        p = _preparar()
        por_escenario, contexto = p.por_escenario, p.contexto
        matrices: list[Matriz] = [crear_matriz(e, por_escenario[e.numero], contexto) for e in ESCENARIOS]

        print("Calculando análisis (incluye la referencia al azar)...")
        tablas = construir_analisis(matrices, p.dias, contexto, p.atr_dia, p.volumen_dia)

        print("Escribiendo archivos...")
        escribir_resultados(config.REPORTE_RESULTADOS, por_escenario, contexto)
        escribir_analisis(config.REPORTE_ANALISIS, tablas)
    except PermissionError as error:
        print(f"\nNo se pudo guardar: {error.filename}\nCiérralo en Excel y vuelve a ejecutar.")
        return 1

    print(f"\nListo en {time.time() - inicio:.0f} s")
    for matriz in matrices:
        conteo = Counter(m.ejecucion for m in matriz.mediciones)
        print(f"Escenario {matriz.escenario.numero}: {dict(conteo)}")
    print(f"Archivos en: {config.CARPETA_MFE_MAE}")
    return 0


def simular() -> int:
    from simulador.principal import ejecutar

    inicio = time.time()
    try:
        p = _preparar()
        print("\nSimulador de combinaciones...")
        atr_ny = {fila: ctx.atr_senal for fila, ctx in p.contexto.items()}
        resumen = ejecutar(p.validacion.senales, p.por_escenario, p.dias, atr_ny)
    except PermissionError as error:
        print(f"\nNo se pudo guardar: {error.filename}\nCiérralo en Excel y vuelve a ejecutar.")
        return 1
    print(f"\nListo en {time.time() - inicio:.0f} s")
    print(f"Ejecutadas por escenario: {resumen['ejecutadas']}")
    print(f"Formas de operar por nivel: {resumen['niveles']}")
    print(f"Archivos en: {config.CARPETA_COMBINACIONES}")
    return 0


def principal() -> int:
    from simulador.principal_escenarios import ejecutar_principal

    inicio = time.time()
    try:
        escenarios = [Escenario(n, d, ms, desl, config.LIMITE_REENTRADA_PRINCIPAL) for n, d, ms, desl, _ in config.ESCENARIOS_PRINCIPAL]
        p = _preparar(escenarios)
        print("\nEntregable principal...")
        atr_ny = {fila: ctx.atr_senal for fila, ctx in p.contexto.items()}
        minutos = {n: m for n, *_, m in config.ESCENARIOS_PRINCIPAL}
        resumen = ejecutar_principal(p.validacion.senales, p.por_escenario, minutos, p.dias, atr_ny)
    except PermissionError as error:
        print(f"\nNo se pudo guardar: {error.filename}\nCiérralo en Excel y vuelve a ejecutar.")
        return 1
    print(f"\nListo en {time.time() - inicio:.0f} s")
    for clave, valor in resumen.items():
        print(f"{clave}: {valor}")
    print(f"Archivos en: {config.CARPETA_PRINCIPAL}")
    return 0


def validar() -> int:
    inicio = time.time()
    try:
        _ejecutar_validacion()
    except PermissionError as error:
        print(f"\nNo se pudo guardar el reporte: {error.filename}\nCiérralo en Excel y vuelve a ejecutar.")
        return 1
    print(f"\nListo en {time.time() - inicio:.0f} s")
    return 0


COMANDOS = {"validar": validar, "medir": medir, "simular": simular, "principal": principal}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMANDOS:
        print("Uso: python main.py validar | medir | simular | principal")
        sys.exit(2)
    sys.exit(COMANDOS[sys.argv[1]]())
