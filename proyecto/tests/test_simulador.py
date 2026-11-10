from datetime import date

import numpy as np
import polars as pl
import pytest

import config
from medicion.entrada import crear_dia
from simulador import metricas as mt
from simulador import salidas
from simulador.indicadores import adx, atr, choppiness, rango_verdadero
from simulador.operaciones import Operacion, crear_operacion
from simulador.reglas_dia import aplicar
from simulador.velas_sesion import agrupar

S = 1_000_000_000
T = 1_000_000 * S  # cierre de la vela de confirmación


def op_sintetica(favor: list[int], cierres: list[int], te: int = 1) -> Operacion:
    """Un tick por segundo desde la entrada; `cierres` son índices del primer tick tras cada cierre."""
    n = len(favor)
    cierres = cierres + [n - 1] * (config.SIM_VELAS_CAMINO - len(cierres))
    return Operacion(0, "20260914", date(2026, 9, 14), "Canal", "Buy", te, T, T, T + np.arange(n) * S, np.array(favor, dtype=np.int64), np.array(cierres))


def test_cuadricula_de_10_a_140_5_usd():
    assert len(config.SIM_TICKS) == 88
    assert config.SIM_TICKS[0] * config.USD_POR_TICK == 10
    assert config.SIM_TICKS[-1] * config.USD_POR_TICK == 140.5
    assert set(np.diff(config.SIM_TICKS)) == {3}


def test_crear_operacion_cuenta_la_vela_de_entrada_como_primera():
    ns = [T + i * S // 2 for i in range(800)]  # un tick cada medio segundo durante 400 s
    tabla = pl.DataFrame({"ns": ns, "last": [100] * 800, "vol": [1] * 800}, schema={"ns": pl.Int64, "last": pl.Int32, "vol": pl.Int32})
    dia = crear_dia(tabla, T)
    op = crear_operacion(0, "20260914", date(2026, 9, 14), "Canal", "Sell", 2, dia, 1, 103, -1, T, velas=3)
    # Te 2: la vela de entrada cierra a T + 120 s; luego T + 240 s y T + 360 s
    assert [int((op.ns[i] - T) // S) for i in op.cierres] == [120, 240, 360]
    assert op.favor[0] == 3  # venta: entrada 103, precio 100


def test_tp_exige_pasar_dos_ticks():
    sl, tp = np.array([50]), np.array([20])
    casi = op_sintetica([0, 10, 21, 5, 0], [4])
    valor, _ = salidas.fijo(casi, 1, sl, tp)
    assert valor[0, 0] == 0 - 2  # no llegó a 22: cierra por tiempo con el tick 4
    llega = op_sintetica([0, 10, 22, 5, 0], [4])
    valor, indice = salidas.fijo(llega, 1, sl, tp)
    assert valor[0, 0] == 20 and indice[0, 0] == 2


def test_sl_sale_al_precio_del_tick_que_salta():
    op = op_sintetica([0, -10, -50, 0, 0], [4])
    valor, indice = salidas.fijo(op, 1, np.array([20]), np.array([100]))
    assert valor[0, 0] == -52 and indice[0, 0] == 2


def test_cierre_por_tiempo_usa_el_primer_tick_tras_el_cierre():
    op = op_sintetica([0, 5, 8, 12, 30, 40], [3, 5])
    valor, indice = salidas.fijo(op, 1, np.array([100]), np.array([100]))
    assert valor[0, 0] == 12 - 2 and indice[0, 0] == 3
    valor, _ = salidas.fijo(op, 2, np.array([100]), np.array([100]))
    assert valor[0, 0] == 40 - 2


def test_breakeven_cierra_en_la_entrada():
    op = op_sintetica([0, 45, 10, -1, -60, 0], [5])
    valor, indice, cerrada = salidas.breakeven(op, 1, 40, np.array([50]), np.array([100]))
    assert valor[0, 0] == -1 - 2 and indice[0, 0] == 3 and cerrada[0, 0]
    sin_be, _ = salidas.fijo(op, 1, np.array([50]), np.array([100]))
    assert sin_be[0, 0] == -60 - 2


def test_breakeven_no_actua_si_el_sl_llega_antes():
    op = op_sintetica([0, -60, 45, 0, 0], [4])
    valor, _, cerrada = salidas.breakeven(op, 1, 40, np.array([50]), np.array([100]))
    assert valor[0, 0] == -62 and not cerrada[0, 0]


def test_niveles_del_sl_por_tiempo():
    assert salidas.niveles_sl_tiempo(np.array([180]), 6, 0)[0] == 180
    assert [int(salidas.niveles_sl_tiempo(np.array([180]), 6, j)[0]) for j in range(6)] == [180, 150, 120, 90, 60, 30]


def test_sl_por_tiempo_se_acerca_al_cerrar_cada_vela():
    # Vela 1: índices 0-2; vela 2: 3-5; vela 3: 6-8. Con SL 180 y 6 velas: 180, luego 150, luego 120.
    favor = [0, -130, -10, -140, 0, 0, -125, 0, 0, 0]
    op = op_sintetica(favor, [3, 6, 9, 9, 9, 9])
    valor, indice = salidas.sl_tiempo(op, 6, np.array([180]), np.array([250]))
    assert indice[0, 0] == 6 and valor[0, 0] == -127
    fijo, _ = salidas.fijo(op, 6, np.array([180]), np.array([250]))
    assert fijo[0, 0] == 0 - 2


def test_salida_parcial_por_contrato():
    op = op_sintetica([0, 102, 10, -1, 0, 0], [5])
    valores, indices, nombres = salidas.parcial(op, 1)
    i = nombres.index("SL 100 · TP1 100 · TP2 120 · breakeven")
    assert valores[i] == (100 + (-1 - 2)) / 2 and indices[i] == 3


def test_solapamiento_pierde_la_senal_solo_si_sigue_dentro():
    entrada = np.array([0, 5, 10])
    salida = np.array([[10], [20], [30]])
    tomada = mt.tomar_sin_solape(entrada, salida)
    assert tomada[:, 0].tolist() == [True, False, True]


def test_las_19_columnas_con_un_caso_a_mano():
    valores = np.array([[10.0], [-5.0], [20.0], [-8.0]], dtype=np.float32)
    salida = np.array([[2], [4], [6], [8]], dtype=np.int64)
    entrada = np.array([1, 3, 5, 7], dtype=np.int64)
    tomada = np.ones((4, 1), dtype=bool)
    col = mt.columnas(valores, salida, tomada, entrada, entrada - 1, np.array([0, 0, 1, 1]), 2, 3, 2, True)
    assert col["Ganancia Neta"][0] == 17
    assert col["Profit Factor"][0] == pytest.approx(30 / 13)
    assert col["Win Rate"][0] == 50
    assert col["Payoff Ratio"][0] == pytest.approx(15 / 6.5)
    assert col["Drawdown"][0] == 8  # pico 25 tras el tercer trade, cae a 17
    assert col["Recovery Factor"][0] == pytest.approx(17 / 8)
    assert col["Trades +"][0] == 2 and col["Trades -"][0] == 2
    assert col["Racha Max. (Trades -)"][0] == 1
    assert col["$ Peor Dia"][0] == 5 and col["Fecha Peor Dia"][0] == 0
    assert col["Racha Max. (Dias -)"][0] == 0
    assert col["Revision Invalida"][0] == 3 and col["No Ejecutadas"][0] == 2
    assert col["Trades (Solapamiento)"][0] == 0


def test_sin_perdidas_el_profit_factor_queda_vacio():
    col = mt.columnas(np.array([[5.0]], dtype=np.float32), np.array([[2]]), np.ones((1, 1), bool), np.array([1]), np.array([0]), np.array([0]), 1, 0, 0, False)
    assert np.isnan(col["Profit Factor"][0])


def test_fuera_de_muestra_no_mira_la_semana_que_califica():
    # Combinación 0: gana mucho solo en la semana 0. Combinación 1: gana poco en todas.
    neto = np.array([[100.0, 5.0], [-10.0, 5.0], [-10.0, 5.0], [-10.0, 5.0]])
    s = mt.Semanal(neto, np.maximum(neto, 0), np.maximum(-neto, 0), np.ones_like(neto))
    assert mt.dentro_de_muestra(s, None).elegidas[0] == 0
    fuera = mt.fuera_de_muestra(s, None)
    assert fuera.elegidas[0] == 1  # sin la semana 0, la combinación 0 pierde
    assert fuera.neto == 5 + 3 * -10  # semanas 1-3: la 0 gana en las otras (100 - 20 > 15)


def test_pbo_detecta_una_ganadora_por_azar():
    azar = np.random.default_rng(1)
    neto = azar.normal(0, 1, (8, 200))
    s = mt.Semanal(neto, np.maximum(neto, 0), np.maximum(-neto, 0), np.ones_like(neto))
    assert 0.2 < mt.pbo(s) < 0.8  # sin ventaja real, la mejor queda bajo la mediana muchas veces


def test_atr_como_ninjatrader():
    h = np.array([10.0, 12, 11, 15])
    l = np.array([8.0, 9, 9, 10])
    c = np.array([9.0, 11, 10, 14])
    tr = rango_verdadero(h, l, c)
    assert tr.tolist() == [2, 3, 2, 5]
    a = atr(h, l, c, 3)
    assert a[0] == 2 and a[1] == pytest.approx((1 * 2 + 3) / 2) and a[2] == pytest.approx((2 * a[1] + 2) / 3)
    assert a[3] == pytest.approx((2 * a[2] + 5) / 3)


def test_indicadores_no_usan_velas_futuras():
    azar = np.random.default_rng(2)
    c = np.cumsum(azar.normal(0, 1, 60)) + 100
    h, l = c + 1, c - 1
    base = (atr(h, l, c, 10), adx(h, l, c, 14), choppiness(h, l, c, 14))
    h2 = h.copy()
    h2[40:] += 50
    otro = (atr(h2, l, c, 10), adx(h2, l, c, 14), choppiness(h2, l, c, 14))
    for a, b in zip(base, otro):
        assert np.allclose(a[:40], b[:40], equal_nan=True)


def test_adx_empieza_en_50():
    h = np.array([10.0, 11, 12])
    l = np.array([9.0, 10, 11])
    c = np.array([9.5, 10.5, 11.5])
    assert adx(h, l, c, 14)[0] == 50


def test_velas_de_dos_minutos_respetan_el_orden():
    velas = pl.DataFrame({
        "serie": [0, 0, 0, 0], "minuto": [10, 11, 12, 13],
        "open": [1, 5, 7, 2], "high": [6, 9, 8, 4], "low": [0, 4, 2, 1], "close": [5, 7, 3, 2], "vol": [1, 2, 3, 4],
    })
    dos = agrupar(velas, 2)
    assert dos.rows() == [(0, 10, 1, 9, 0, 7, 3), (0, 12, 7, 8, 1, 2, 7)]


def test_regla_maximo_una_operacion_por_dia():
    valores = np.array([1.0, -1.0, 2.0])
    entrada = np.array([1, 5, 9])
    salida = np.array([2, 6, 10])
    dia = np.array([0, 0, 1])
    tomadas = aplicar(valores, entrada, salida, dia, lambda k, e: e.operaciones < 1)
    assert tomadas.tolist() == [0, 2]
