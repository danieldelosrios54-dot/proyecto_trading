"""Entregable principal: cierre por minutos, SL − 2, columnas de vecinas y consistencia, conclusiones."""

from datetime import date

import numpy as np

import config
from simulador import metricas as mt
from simulador import salidas
from simulador.operaciones import Operacion
from simulador.principal_escenarios import COLUMNAS_20, COLUMNAS_ZONAS, CONSISTENCIA, comparar

S = 1_000_000_000
T = 1_000_000 * S


def op_por_segundos(favor: list[int], te: int = 1) -> Operacion:
    """Un tick por segundo desde la entrada."""
    n = len(favor)
    return Operacion(0, "20260914", date(2026, 9, 14), "Canal", "Buy", te, T, T, T + np.arange(n) * S, np.array(favor, dtype=np.int64), np.full(config.SIM_VELAS_CAMINO, n - 1))


def test_cierre_por_minutos_igual_en_te_1_y_te_2():
    favor = [0] * 700
    favor[540] = 15  # a los 9 minutos exactos
    for te in (1, 2):
        op = op_por_segundos(favor, te)
        valor, indice = salidas.fijo_minutos(op, 9, np.array([200]), np.array([200]))
        assert indice[0, 0] == 540 and valor[0, 0] == 15 - 2


def test_sl_sale_al_precio_del_sl_menos_dos_aunque_salte():
    op = op_por_segundos([0, -10, -60, 0] + [0] * 600)
    valor, indice = salidas.fijo_minutos(op, 9, np.array([20]), np.array([100]))
    assert valor[0, 0] == -22 and indice[0, 0] == 2


def test_combinaciones_vecinas_centro_borde_y_esquina():
    neto = np.arange(16, dtype=float).reshape(4, 4)
    neto[1, 2] = -50
    v = mt.combinaciones_vecinas(neto.ravel(), 4).reshape(4, 4)
    assert v[0, 0] == 0  # esquina: mínimo de 4
    assert v[1, 1] == -50  # centro: incluye la vecina negativa
    assert v[3, 3] == 10  # esquina inferior: 10, 11, 14, 15
    assert v[0, 3] == -50  # borde superior derecho alcanza (1, 2)


def test_peor_mitad_y_semanas_positivas():
    neto = np.array([[10.0, -5.0], [20.0, -5.0], [-1.0, 30.0], [-2.0, 1.0]])
    ops = np.array([[1, 1], [1, 1], [1, 1], [0, 0]], dtype=float)
    s = mt.Semanal(neto, np.maximum(neto, 0), np.maximum(-neto, 0), ops)
    assert mt.peor_mitad(s).tolist() == [-3.0, -10.0]
    positivas, con_ops = mt.semanas_positivas(s)
    assert con_ops == 3 and positivas.tolist() == [2, 1]


def test_columnas_por_archivo():
    assert len(COLUMNAS_20) == 20 and not set(CONSISTENCIA) & set(COLUMNAS_20)
    assert "Profit Factor" not in COLUMNAS_ZONAS and "# Solapamiento" not in COLUMNAS_ZONAS
    assert set(CONSISTENCIA) <= set(COLUMNAS_ZONAS)


def test_comparar_exige_total_y_ambas_mitades():
    a = mt.Calificacion(100, 10, 1.2, 8, 60, 40, ())
    b = mt.Calificacion(50, 10, 1.1, 7, 30, 20, ())
    c = mt.Calificacion(120, 10, 1.3, 7, 110, 10, ())
    assert comparar(a, b) == "a" and comparar(b, a) == "b"
    assert comparar(a, c) == "empate"  # c gana en total pero pierde la segunda mitad
