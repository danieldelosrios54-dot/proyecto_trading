"""Documento 5: posiciones, salidas nuevas, interruptor del SL y criterios de estado."""

from datetime import date

import numpy as np
import pytest

import config
from simulador import metricas as mt
from simulador import salidas
from simulador import salidas_formas as sf
from simulador.estado_formas import CANDIDATA, DESCARTADA, OBSERVACION, Evaluacion, decidir
from simulador.operaciones import Minutos, Operacion
from simulador.posiciones import orden_con_prioridad, tomar

S = 1_000_000_000
T = 1_000_000 * S


def op_seg(favor: list[int], cierres: list[int] | None = None, te: int = 1) -> Operacion:
    n = len(favor)
    cierres = (cierres or []) + [n - 1] * (config.SIM_VELAS_CAMINO - len(cierres or []))
    return Operacion(0, "20260914", date(2026, 9, 14), "Canal", "Buy", te, T, T, T + np.arange(n) * S, np.array(favor, dtype=np.int64), np.array(cierres))


@pytest.fixture
def sl_al_precio():
    salidas.SL_AL_PRECIO = True
    yield
    salidas.SL_AL_PRECIO = False


def test_una_posicion_igual_que_el_solapamiento_actual():
    azar = np.random.default_rng(3)
    entrada = np.sort(azar.integers(0, 1000, 40))
    salida = entrada[:, None] + azar.integers(1, 80, (40, 5))
    signo = azar.choice([1, -1], 40)
    assert (tomar(entrada, salida, signo, 1) == mt.tomar_sin_solape(entrada, salida)).all()


def test_varias_posiciones_solo_en_la_misma_direccion():
    entrada = np.array([0, 5, 6, 7])
    salida = np.array([[100], [100], [100], [100]])
    signo = np.array([1, 1, -1, 1])
    t = tomar(entrada, salida, signo, 2)[:, 0]
    assert t.tolist() == [True, True, False, False]  # la venta se pierde; la tercera compra excede el máximo


def test_separacion_minima_entre_entradas():
    entrada = np.array([0, 3, 12])
    salida = np.array([[1], [4], [13]])
    assert tomar(entrada, salida, np.ones(3, int), 1, separacion_ns=10)[:, 0].tolist() == [True, False, True]


def test_prioridad_en_el_mismo_instante():
    entrada = np.array([5, 5])
    salida = np.array([[50], [50]])
    orden = orden_con_prioridad(entrada, np.array([1, 0]))
    assert tomar(entrada, salida, np.ones(2, int), 1, orden=orden)[:, 0].tolist() == [False, True]


def test_sl_al_precio_aunque_el_tick_salte(sl_al_precio):
    op = op_seg([0, -10, -50, 0, 0])
    v, _ = salidas.fijo(op, Minutos(10), np.array([20]), np.array([100]))
    assert v[0, 0] == -22


def test_cierre_condicionado_deja_correr_si_va_ganando(sl_al_precio):
    favor = [0] * 900
    favor[540:700] = [20] * 160  # a los 9 minutos va ganando y sigue arriba
    # en el tick 700 (11:40) vuelve a la entrada
    op = op_seg(favor)
    v, i = sf.condicional(op, 9, 6, np.array([200]), np.array([200]))
    assert i[0, 0] == 700 and v[0, 0] == -2
    favor[540] = -5  # si va perdiendo, cierra a los 9 minutos
    v, i = sf.condicional(op_seg(favor), 9, 6, np.array([200]), np.array([200]))
    assert i[0, 0] == 540 and v[0, 0] == -7


def test_corte_temprano():
    favor = [0] * 700
    favor[120] = -70
    v, i = sf.corte_temprano(op_seg(favor), 9, 2, 60, np.array([200]), np.array([200]))
    assert i[0, 0] == 120 and v[0, 0] == -72


def test_trailing_por_velas_sube_al_minimo_de_la_vela_a_favor(sl_al_precio):
    # Vela 1 (0-2) cierra a favor con mínimo 5; en la vela 2 el precio cae a 4: salida al nivel 5 − 2.
    favor = [5, 8, 12, 4, 30, 30] + [30] * 600
    v, i = sf.trailing_velas(op_seg(favor, [3, 6]), 9, np.array([100]), np.array([500]))
    assert i[0, 0] == 3 and v[0, 0] == 3


def test_salida_por_senal_contraria():
    favor = [0, 5, 10, 15] + [20] * 600
    v, i = sf.contraria(op_seg(favor), 9, 3, np.array([100]), np.array([500]))
    assert i[0, 0] == 3 and v[0, 0] == 13


def test_tp_proporcional_al_atr():
    favor = [0, 50, 102] + [0] * 600
    v, _ = sf.tp_proporcional(op_seg(favor), 9, 100.0, np.array([1.0]), np.array([200]))
    assert v[0, 0] == 100


def _ev(neto, m1, m2, caida=500.0, semanas=None, sp=8):
    cal = mt.Calificacion(neto, 100, 1.2, sp, m1, m2, ())
    return Evaluacion(cal, cal, np.array(semanas if semanas is not None else [neto / 14] * 14), caida)


def test_criterios_de_estado():
    ref = _ev(1000, 600, 400)
    assert decidir(_ev(-50, 100, -150), ref, 0)[0] == DESCARTADA
    assert decidir(_ev(1200, 700, 500), ref, 0)[0] == CANDIDATA
    assert decidir(_ev(900, 1000, -100), ref, 0)[0] == OBSERVACION
    peor = _ev(300, 200, 100, caida=900, semanas=[ref.semanas[0] - 50] * 14, sp=5)
    estado, argumento = decidir(peor, ref, 0)
    assert estado == DESCARTADA and "no da valor" in argumento
    assert decidir(_ev(1200, 700, 500), ref, 5000)[0] == OBSERVACION  # no supera al azar


def _con_top(ev, positivas, ambas_todas):
    ev.top = {"combinaciones": 100, "positivas": positivas, "ambas_todas": ambas_todas}
    return ev


def test_candidata_no_puede_depender_de_una_epoca_mas_que_la_referencia():
    ref = _con_top(_ev(1000, 600, 400), 40, 11)  # 27,5 %
    estado, argumento = decidir(_con_top(_ev(1200, 700, 500), 40, 11), ref, 0)
    assert estado == CANDIDATA and "11 de 40 combinaciones positivas ganan en ambas mitades (28 %; la referencia: 28 %)" in argumento
    estado, argumento = decidir(_con_top(_ev(1200, 700, 500), 40, 10), ref, 0)
    assert estado == OBSERVACION and "depende más de una época" in argumento
    assert decidir(_con_top(_ev(1200, 700, 500), 0, 0), ref, 0)[0] == OBSERVACION
    # la referencia cumple por definición
    assert decidir(ref, ref, 0, es_referencia=True)[0] == CANDIDATA
    # sin tabla de combinaciones el criterio no aplica
    assert "no aplica" in decidir(_ev(1200, 700, 500), ref, 0)[1]
