"""Top 20 de cada escenario y tabla de resumen."""

import numpy as np

from simulador import metricas as mt
from simulador.estado_formas import CANDIDATA, DESCARTADA, NO_APLICA, NO_MEDIDA, OBSERVACION, Evaluacion
from simulador.formas import Fila, resumen_top
from simulador.resumen_escenarios import ENCABEZADOS, POR_QUE, tablas


def test_resumen_top_cuenta_positivas_mitades_y_caida():
    # 4 semanas, 3 combinaciones; una operación por semana
    neto = np.array([[10.0, -5.0, 1.0], [10.0, -5.0, 1.0], [-30.0, -5.0, 1.0], [20.0, -5.0, -9.0]])
    s = mt.Semanal(neto, np.maximum(neto, 0), np.maximum(-neto, 0), np.ones_like(neto))
    valores = neto.astype(np.float32)
    salida = np.arange(4)[:, None].repeat(3, 1).astype(np.int64)
    tomada = np.ones((4, 3), dtype=bool)
    r = resumen_top(s, valores, salida, tomada, None, n=2)
    assert r["combinaciones"] == 3 and r["positivas"] == 1
    assert r["ambas_todas"] == 0  # la única positiva (0) pierde la segunda mitad
    assert r["ganancia"] == (10 + -6) / 2  # top 2: combinaciones 0 (10) y 2 (−6)
    assert r["ambas"] == 0  # la combinación 0 pierde la segunda mitad (−10)
    assert r["caida"] == (30 + 9) / 2  # caídas: 30 en la 0 (de 20 a −10) y 9 en la 2


def _ev(fuera_neto: float, ambas_todas: int = 3) -> Evaluacion:
    cal = mt.Calificacion(fuera_neto, 100, 1.2, 8, fuera_neto / 2, fuera_neto / 2, ())
    top = {"combinaciones": 10, "positivas": 4, "ambas_todas": ambas_todas, "ganancia": 500.0, "ganancia_min": 400.0, "ganancia_max": 600.0,
           "mitad1": 300.0, "mitad2": 200.0, "ambas": 15, "caida": 800.0, "pf": 1.2, "operaciones": 400.0, "vecinas": 12, "n": 20}
    return Evaluacion(cal, cal, np.zeros(14), 800.0, "", None, top)


def test_tabla_de_resumen_ordena_por_estado_y_explica_el_motivo():
    filas = [
        Fila("4", "Selección", "Otra forma", _ev(100.0), estado=DESCARTADA, argumento="Negativa en semanas no vistas. Fuera de muestra…"),
        Fila("10", "Entrada", "Deslizamiento de entrada de 6 ticks", _ev(500.0), estado=NO_APLICA, argumento="No aplica: es un costo. Fuera de muestra…"),
        Fila("14", "Selección", "Noticias", None, estado=NO_MEDIDA, argumento="Falta el calendario de noticias."),
        Fila("Nueva", "Salida", "Forma frágil", _ev(2000.0, 1), estado=OBSERVACION, argumento="Positiva en semanas no vistas, pero depende de una época. Fuera de muestra…"),
        Fila("1", "Salida", "ATM fijo (referencia)", _ev(3000.0), estado=CANDIDATA, argumento="Escenario de referencia: positivo. Fuera de muestra…"),
    ]
    mapa = [(5, 100, 8, "Todas", _ev(4000.0), CANDIDATA, "Positiva… Fuera de muestra…"), (3, 200, 9, "Todas", _ev(3000.0), CANDIDATA, "Positiva… Fuera de muestra…")]
    resumen = tablas(filas, mapa, 3000.0, _ev(3000.0).top)[0]
    assert resumen.encabezados == ENCABEZADOS and "Recomendación" not in ENCABEZADOS
    col = {n: ENCABEZADOS.index(n) for n in ("Escenario", "Estado", POR_QUE, "Combinaciones positivas", "Combinaciones + 2 mitades")}
    assert [f[col["Escenario"]] for f in resumen.filas] == [
        "Mapa: ±5 ticks · 100 ms · 8 min · Todas", "ATM fijo (referencia)", "Mapa: ±3 ticks · 200 ms · 9 min · Todas",
        "Forma frágil", "Otra forma", "Deslizamiento de entrada de 6 ticks", "Noticias"]
    assert [f[col["Estado"]] for f in resumen.filas] == [CANDIDATA, CANDIDATA, CANDIDATA, OBSERVACION, DESCARTADA, NO_APLICA, NO_MEDIDA]
    motivos = [f[col[POR_QUE]] for f in resumen.filas]
    assert "velocidad real" in motivos[0] and "3 de 4 combinaciones positivas ganan en ambas mitades (75 %; la referencia: 75 %)" in motivos[0]
    assert "misma regla que la referencia" in motivos[2]
    assert "1 de 4 combinaciones positivas" in motivos[3]
    assert motivos[4] == "Negativa en semanas no vistas. Fuera de muestra +100 USD; diferencia con la referencia -2.900 USD."
    assert motivos[6] == "Falta el calendario de noticias."
    assert resumen.filas[1][col["Combinaciones positivas"]] == "4 de 10 (40 %)"
    assert resumen.filas[1][col["Combinaciones + 2 mitades"]] == "3 de 10 (30 %)"
