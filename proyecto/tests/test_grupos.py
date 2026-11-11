"""Grupos de escenarios y zona de combinaciones utilizables por grupo."""

from datetime import date

import numpy as np

from simulador import metricas as mt
from simulador.datos import LADO
from simulador.estado_formas import CANDIDATA, DESCARTADA, OBSERVACION, Evaluacion
from simulador.formas import Fila, consistente, meses_de_semanas
from simulador.principal_escenarios import COLUMNAS_20
from simulador.resumen_escenarios import GRUPO_REFERENCIA, GRUPO_SIN_TREND_V, GRUPOS_ENCABEZADOS, grupo, tablas, utilizables


def test_grupo_junta_variantes_de_la_misma_idea():
    assert grupo("Mapa: ±5 ticks · 100 ms · 8 min · Todas", "Mapa de reglas") == GRUPO_REFERENCIA
    assert grupo("ATM fijo (referencia)", "Forma de operar") == GRUPO_REFERENCIA
    assert grupo("Mapa: ±3 ticks · 200 ms · 9 min · Sin Trend ≥ 2do Pivot ni V", "Mapa de reglas") == GRUPO_SIN_TREND_V
    assert grupo("Dejar de operar Trend ≥ 2do Pivot y V", "Forma de operar") == GRUPO_SIN_TREND_V
    assert grupo("Dejar de operar I. Fuerte en Te 1 (124 señales)", "Forma de operar") == "Dejar de operar I. Fuerte"
    assert grupo("Dejar de operar I. Fuerte / V en Te 2 (20 señales)", "Forma de operar") == "Dejar de operar I. Fuerte / V"
    assert grupo("Corte temprano: a los 2 min, si va 100 ticks o más en contra, salir", "Forma de operar") == "Corte temprano"
    assert grupo("No operar si la orden está a más de 30 ticks del cierre de la vela", "Forma de operar") == "No operar órdenes lejanas del cierre de la vela"
    # filtros distintos no se juntan
    assert grupo("Dejar de operar con estructura M = A", "Forma de operar") != grupo("Dejar de operar con estructura M = B", "Forma de operar")
    assert grupo("Stop al cierre de vela", "Forma de operar") == "Stop al cierre de vela"


def _ev_combinaciones(total, primera, segunda, lado=None, nombres=None, elegidas=()) -> Evaluacion:
    cal = mt.Calificacion(100.0, 10, 1.2, 8, 50.0, 50.0, ())
    pc = {"total": np.asarray(total, np.float32), "primera": np.asarray(primera, np.float32), "segunda": np.asarray(segunda, np.float32),
          "lado": lado, "nombres": nombres, "elegidas": list(elegidas)}
    return Evaluacion(cal, cal, np.zeros(14), 100.0, "", None, {"por_combinacion": pc})


def test_utilizables_exige_ganar_en_ambas_mitades_en_todas_las_candidatas():
    nombres = ["A", "B", "C"]
    e1 = _ev_combinaciones([100, 80, 50], [60, 50, 20], [40, 30, 30], nombres=nombres, elegidas=[0, 1, 2, 0])
    e2 = _ev_combinaciones([90, 70, 40], [50, -10, 10], [40, 80, 30], nombres=nombres, elegidas=[1, 1, 0, 0])
    zona = utilizables([e1, e2])
    assert zona["texto"] == "2 de 3 combinaciones en las 2 candidatas del grupo."  # B pierde la 1ª mitad en e2
    assert zona["ok"].tolist() == [True, False, True]
    assert zona["referencia"] == "A; neto mínimo entre escenarios +90 USD"
    assert zona["elecciones"] == "5 de 8 (62 %)"  # elegidas dentro de la zona: 0,2,0 en e1 y 0,0 en e2


def test_utilizables_en_la_cuadricula_informa_rango_y_vecinas():
    n = LADO * LADO
    total, mitad = np.full(n, -1.0), np.full(n, -1.0)
    for sl in (10, 11, 12):
        for tp in (5, 6, 7):
            i = sl * LADO + tp
            total[i], mitad[i] = 100.0 + (50 if (sl, tp) == (11, 6) else 0), 50.0
    zona = utilizables([_ev_combinaciones(total, mitad, mitad, lado=LADO)])
    assert zona["texto"] == "9 de 7.744 combinaciones en su candidata: SL entre 25 y 28 USD, TP entre 17,5 y 20,5 USD."
    assert zona["referencia"] == "SL 26,5 / TP 19 USD; neto mínimo entre escenarios +150 USD; 8 de 8 vecinas utilizables"


def test_utilizables_sin_candidatas_o_sin_tabla():
    assert utilizables([])["texto"].startswith("No aplica: ningún escenario")
    cal = mt.Calificacion(100.0, 10, 1.2, 8, 50.0, 50.0, ())
    assert utilizables([Evaluacion(cal, cal, np.zeros(14), 1.0)])["texto"].startswith("No aplica: sus candidatas eligen el ATM")


def test_pestana_grupos_cuenta_por_idea():
    def ev(neto, pos):
        cal = mt.Calificacion(neto, 100, 1.2, 8, neto / 2, neto / 2, ())
        top = {"combinaciones": 3, "positivas": 2, "ambas_todas": 1, "ganancia": 1.0, "mitad1": 1.0, "mitad2": 1.0, "ambas": 1, "caida": 1.0,
               "operaciones": 1.0, "vecinas": None, "n": 3,
               "por_combinacion": {"total": np.array(pos, np.float32), "primera": np.array(pos, np.float32), "segunda": np.array(pos, np.float32),
                                   "lado": None, "nombres": ["x", "y", "z"], "elegidas": [0]}}
        return Evaluacion(cal, cal, np.zeros(14), 1.0, "", None, top)
    filas = [
        Fila("4", "Selección", "Dejar de operar V", ev(3000, [5, 5, -5]), estado=CANDIDATA, argumento="Positiva."),
        Fila("4", "Selección", "Dejar de operar V en Te 1 (25 señales)", ev(2000, [5, -5, 5]), estado=CANDIDATA, argumento="Positiva."),
        Fila("4", "Selección", "Dejar de operar V en Te 2 (17 señales)", ev(-100, [5, 5, 5]), estado=DESCARTADA, argumento="Negativa."),
        Fila("Nueva", "Salida", "Salir si no reacciona", ev(500, [1, 1, 1]), estado=OBSERVACION, argumento="Positiva, pero…"),
    ]
    pestanas = tablas(filas, [], 3000.0)
    grupos = pestanas[1]
    assert grupos.titulo == "Grupos" and grupos.encabezados == GRUPOS_ENCABEZADOS
    v = grupos.filas[0]
    assert v[:6] == ["Dejar de operar V", 3, 2, 0, 1, 0]
    assert v[9] == "Dejar de operar V"  # mejor escenario entre sus candidatas
    assert v[10] == "1 de 3 combinaciones en las 2 candidatas del grupo."  # solo "x" gana en ambas candidatas
    assert grupos.filas[1][0] == "Salir si no reacciona" and grupos.filas[1][10].startswith("No aplica: ningún escenario")
    assert pestanas[2].filas == []  # sin columnas guardadas no hay detalle


def test_meses_por_el_miercoles_de_cada_semana():
    semanas = [date(2026, 6, 29), date(2026, 7, 27), date(2026, 8, 3), date(2026, 8, 24), date(2026, 8, 31), date(2026, 9, 28)]
    meses, nombres = meses_de_semanas(semanas)
    assert meses.tolist() == [0, 0, 1, 1, 2, 2] and nombres == ["Julio", "Agosto", "Septiembre"]


def test_perder_un_mes_deja_de_ser_utilizable():
    pc = {"total": np.array([100.0, 100.0]), "primera": np.array([50.0, 50.0]), "segunda": np.array([50.0, 50.0]),
          "meses": np.array([[40.0, 60.0], [30.0, 50.0], [30.0, -10.0]])}  # la segunda pierde septiembre
    assert consistente(pc).tolist() == [True, False]


def test_detalle_una_fila_por_combinacion_y_escenario_candidato():
    def ev(neto, pos):
        cal = mt.Calificacion(neto, 100, 1.2, 8, neto / 2, neto / 2, ())
        arr = np.array(pos, np.float32)
        columnas = {"indices": np.array([0, 1, 2])}
        columnas.update({n: np.array([float(neto + k) for k in range(3)]) for n in COLUMNAS_20})
        columnas["Fecha Peor Dia"] = np.array([-1, -1, -1])
        top = {"combinaciones": 3, "positivas": 2, "ambas_todas": 1, "ganancia": 1.0, "mitad1": 1.0, "mitad2": 1.0, "ambas": 1, "caida": 1.0,
               "operaciones": 1.0, "vecinas": None, "n": 3,
               "por_combinacion": {"total": arr, "primera": arr, "segunda": arr, "meses": np.vstack([arr, arr, arr]),
                                   "nombres_meses": ["Julio", "Agosto", "Septiembre"], "lado": None, "nombres": ["x", "y", "z"],
                                   "elegidas": [0], "columnas": columnas}}
        return Evaluacion(cal, cal, np.zeros(14), 1.0, "", None, top)
    filas = [
        Fila("4", "Selección", "Dejar de operar V", ev(3000, [5, 5, -5]), estado=CANDIDATA, argumento="Positiva."),
        Fila("4", "Selección", "Dejar de operar V en Te 1 (25 señales)", ev(2000, [5, -5, 5]), estado=CANDIDATA, argumento="Positiva."),
    ]
    detalle = tablas(filas, [], 3000.0)[2]
    assert detalle.encabezados[:7] == ["Grupo", "Escenario", "SL (ticks)", "TP (ticks)", "SL (USD)", "TP (USD)", "Parámetro"]
    assert detalle.encabezados[-3:] == ["Julio (USD)", "Agosto (USD)", "Septiembre (USD)"]
    # solo "x" es utilizable en el grupo: una fila por cada escenario candidato, con los resultados de ese escenario
    assert [(f[1], f[6]) for f in detalle.filas] == [("Dejar de operar V", "x"), ("Dejar de operar V en Te 1 (25 señales)", "x")]
    ganancia = detalle.encabezados.index("Ganancia Neta")
    assert [f[ganancia] for f in detalle.filas] == [3000.0, 2000.0]
    assert detalle.filas[0][detalle.encabezados.index("Fecha Peor Dia")] is None


def test_columnas_de_tiempo_no_se_redondean():
    from simulador.resumen_escenarios import _valor
    assert _valor("Prom. Tiempo Abierta", np.float64(0.0034)) == 0.0034  # unos 5 minutos como fracción de día
    assert _valor("Profit Factor", np.float64(1.2345)) == 1.23
