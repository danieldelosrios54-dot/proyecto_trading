"""Rutas, ventanas, umbrales y valores permitidos del proyecto."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Entradas
ARCHIVO_REGISTRO = RAIZ / "entrada" / "registros_señales" / "registro_señales.xlsx"
CARPETA_DATA_TICKS = RAIZ / "entrada" / "data_ticks"

# Salidas
CARPETA_TICKS_EXTRAIDOS = RAIZ / "salida" / "ticks_extraidos"
CARPETA_VALIDACIONES = RAIZ / "salida" / "validaciones"
REPORTE_SENALES = CARPETA_VALIDACIONES / "validacion_señales_registradas.xlsx"
REPORTE_TICKS = CARPETA_VALIDACIONES / "validacion_ticks_extraidos.xlsx"

CARPETA_MFE_MAE = RAIZ / "salida" / "mfe_mae"
REPORTE_RESULTADOS = CARPETA_MFE_MAE / "resultados_mfe_mae.xlsx"
REPORTE_ANALISIS = CARPETA_MFE_MAE / "analisis_mfe_mae.xlsx"

# Excel
HOJA_REGISTRO = "Registro Señales"
HOJA_CONDICIONES = "Condiciones"
FILA_ENCABEZADOS = 2

# Ventana de ticks a extraer, en minutos respecto a "Apertura UTC"
MINUTOS_ANTES_APERTURA = 10
MINUTOS_DESPUES_APERTURA = 90

# Tiempo máximo de posición abierta usado para calcular el tramo de cada señal
MINUTOS_POSICION_ABIERTA = 12

# Umbrales de las reglas de ticks
TICKS_POR_PUNTO = 4
T9_SALTO_TICKS = 60
T10_HUECO_MIN_S = 10
T11_HUECO_MAX_S = 60
T12_FRACCION_MEDIANA = 0.5

# Valores permitidos
ZONA_VC = "1er Vela (VC)"
ZONAS_PRIMERA_VELA = {"1er Vela", ZONA_VC}
ZONAS_IMPULSO = {"I. Fuerte / V", "I. Fuerte", "V"}
ZONAS_CONTINUACION = {"Trend 1er Pivot", "Trend ≥ 2do Pivot", "Fin Trend M/W", "Rango", "Canal"}
ZONAS = ZONAS_PRIMERA_VELA | ZONAS_IMPULSO | ZONAS_CONTINUACION

VALORES_TE = {1, 2}
VALORES_TIPO = {"Buy", "Sell"}
VALORES_OHLC = {"Low", "High", "Close"}
VALORES_M = {"A", "B", "LA", "LM", "LP"}
VALORES_ESTATUS = {"-", "CL", "CF"}
VALORES_D = {"-", "D"}
APERTURAS_UTC_S = {13 * 3600 + 30 * 60, 14 * 3600 + 30 * 60}

HORAS_COLOMBIA_A_UTC = 5
ZONA_HORARIA_NY = "America/New_York"

# Velas máximas entre "Vela OP" y "Hora UTC" (R9)
VELAS_MAX_OP_IMPULSO = 3
VELAS_MAX_OP_CONTINUACION = 1

# Velas de la ventana de ejecución tras la vela de confirmación
VELAS_EJECUCION_CORTA = 1  # primera vela e impulso
VELAS_EJECUCION_LARGA = 2  # continuación

# Medición MFE/MAE: (número, distancia OP en ticks, demora en ms, deslizamiento en ticks)
ESCENARIOS = ((1, 3, 300, 3), (2, 7, 300, 3), (3, 3, 700, 3), (4, 3, 300, 6))
HORIZONTES = tuple(range(1, 11))  # minutos
LIMITE_REENTRADA_TICKS = 45
USD_POR_TICK = 0.5

# Análisis
PORCENTAJES_SENALES = (50, 60, 67, 75, 80, 90)
CUADRICULA_SL_TP = tuple(range(20, 281, 20))  # ticks
NIVELES_MFE = ((None, 50), (50, 100), (100, 200), (200, None))
NIVELES_A_FAVOR = (20, 40, 60, 80, 120)
MUESTRA_MINIMA = 30
AZAR_POR_SENAL = 20
AZAR_SEMILLA = 2026
BOOTSTRAP_REPETICIONES = 300
BOOTSTRAP_SEMILLA = 2026

# Simulador de combinaciones
CARPETA_COMBINACIONES = RAIZ / "salida" / "combinaciones"
CARPETA_VELAS_SESION = RAIZ / "salida" / "velas_sesion"
VELAS_ENTREGABLES = 4  # cierre por tiempo de los entregables 1 a 3
REPORTE_TODAS = CARPETA_COMBINACIONES / f"combinaciones_todas_cierre_{VELAS_ENTREGABLES}_velas.xlsx"
REPORTE_ZONAS = CARPETA_COMBINACIONES / f"combinaciones_zonas_cierre_{VELAS_ENTREGABLES}_velas.xlsx"
REPORTE_SEMANAS = CARPETA_COMBINACIONES / f"combinaciones_semanas_cierre_{VELAS_ENTREGABLES}_velas.xlsx"
REPORTE_ANALISIS_COMBINACIONES = CARPETA_COMBINACIONES / "analisis_combinaciones.xlsx"

SIM_TICKS = tuple(range(20, 282, 3))  # SL y TP: 10 a 140,5 USD cada 1,5
SIM_VELAS = tuple(range(3, 11))  # cierres por tiempo comparados
SIM_VELAS_CAMINO = max(SIM_VELAS)  # velas que se recorren tras la entrada
COMISION_USD = 1.86
TP_EXCESO_TICKS = 2  # el precio debe pasar el TP por 2 ticks
SALIDA_DESLIZ_TICKS = 2  # SL, breakeven y cierre por tiempo
BREAKEVEN_TICKS = (40, 60, 80, 100)
MESETA_PASOS = 2  # vecinas a cada lado al elegir la mejor combinación (5 × 5)

# Otras salidas (parámetros gruesos)
OTRAS_SL = (100, 130, 160, 190, 220, 250)
OTRAS_TP = (60, 80, 100, 120, 160, 200, 250)
PARCIAL_TP1 = (40, 60, 80, 100)
PARCIAL_TP2 = (120, 160, 200, 250)
TRAILING_ACTIVA = (40, 60, 80, 100)
TRAILING_DISTANCIA = (40, 60, 80, 100, 140)
CIERRE_VELA_STOP = (60, 100, 140, 180)
CIERRE_VELA_CATASTROFE = (250, 400)
REACCION_SL = (130, 160, 190, 250)
REACCION_TP = (60, 100, 120, 160, 250)
REACCION_VELA = (1, 2, 3)
REACCION_MINIMO = (10, 20, 40, 60)

# Reglas del día
REGLA_PERDIDA_USD = (50, 100, 150)
REGLA_GANANCIA_USD = (50, 100, 150)
REGLA_MAX_OPERACIONES = (1, 2, 3, 5)
REGLA_PERDIDAS_SEGUIDAS = (1, 2)
REGLA_HORARIOS_MIN = ((0, 20), (0, 30), (10, 70), (20, 40), (30, 70), (40, 70))

# Indicadores (como NinjaTrader 8, horario ETH)
ATR_PERIODOS = (5, 10)
ADX_PERIODO = 14
CHOP_PERIODO = 14
VOLMA_PERIODO = 20
VELAS_APERTURA = 10  # señales "de apertura" frente al resto
SESION_INICIO_HORA_NY = 18
SESION_MARGEN_MIN = 15  # la sesión está completa si tiene velas en sus primeros 15 minutos

# Entregable principal (documento 4)
CARPETA_PRINCIPAL = CARPETA_COMBINACIONES / "principal"
REPORTE_PRINCIPAL = CARPETA_PRINCIPAL / "combinaciones_principal.xlsx"
REPORTE_PRINCIPAL_ZONAS = CARPETA_PRINCIPAL / "combinaciones_principal_zonas.xlsx"
REPORTE_PRINCIPAL_SEMANA = CARPETA_PRINCIPAL / "combinaciones_principal_semana.xlsx"
REPORTE_ANALISIS_PRINCIPAL = CARPETA_PRINCIPAL / "analisis_principal.xlsx"
LIMITE_REENTRADA_PRINCIPAL = 60
# (número, distancia OP en ticks, colocación en ms, deslizamiento en ticks, cierre por tiempo en minutos)
ESCENARIOS_PRINCIPAL = ((1, 3, 200, 3, 9), (2, 7, 200, 3, 9), (3, 3, 600, 3, 9), (4, 3, 200, 6, 9), (5, 3, 200, 3, 8), (6, 3, 200, 3, 5))
ATM_REFERENCIA = (185, 125)  # SL y TP en ticks
CANDIDATAS_MAX = 30

# Documento 5: todas las formas de operar
CARPETA_FORMAS = RAIZ / "salida" / "formas"
REPORTE_FORMAS = CARPETA_FORMAS / "analisis_formas.xlsx"
REPORTE_PROPUESTA_MATRIZ = CARPETA_FORMAS / "propuesta_matriz.xlsx"
REPORTE_RESUMEN_ESCENARIOS = CARPETA_FORMAS / "resumen_escenarios.xlsx"
CALENDARIO_NOTICIAS = RAIZ / "entrada" / "calendario_noticias.csv"
ESCENARIO_FORMAS = (3, 200, 3, 9)  # referencia: distancia, colocación ms, deslizamiento, cierre en minutos
FORMAS_DISTANCIAS = (3, 4, 5, 6, 7)
FORMAS_COLOCACION = (100, 200, 300, 600)
FORMAS_CIERRES = (7, 8, 9, 10, 11)
FORMAS_AZAR = 100

# Validación
AZAR_CARTERAS = 100
AGRUPACIONES_FALSAS = 100

# Ejecución de una señal
EJECUTADA = "Ejecutada"
NO_EJECUTADA = "No Ejecutada"
NO_EJECUTADA_OP = "No Ejecutada OP"

# Revisión de una señal
REVISION_VALIDA = "Valida"
REVISION_INVALIDA_R = "Invalida R"
REVISION_INVALIDA_T = "Invalida T"
REVISION_INVALIDA_OP = "Invalida OP"

# Estados
VALIDA = "Valida"
NOTIFICADA = "Valida con notificación"
INVALIDA = "Invalida"
INVALIDAR = "Invalidar"
NOTIFICAR = "Notificar"
