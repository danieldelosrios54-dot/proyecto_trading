"""Motor de entradas, recorridos, volatilidad y análisis de MFE/MAE."""

from datetime import date, time

import numpy as np
import polars as pl
import pytest

import config
from medicion.analisis import al_menos, clasificar, no_paso_de
from medicion.azar import medir_azar
from medicion.entrada import Escenario, cargar_dia, crear_dia, orden_valida, precio_orden, simular_entrada
from medicion.recorrido import recorridos, tras_ir_a_favor
from medicion.volatilidad import atr_apertura, atr_hasta, volumen_primera_hora
from validacion.extraccion import Ventana, extraer, ruta_parquet
from validacion.modelos import ns_del_dia

FECHA = date(2026, 9, 14)
HORA = ns_del_dia(FECHA, 13 * 3600 + 40 * 60)
APERTURA = ns_del_dia(FECHA, 13 * 3600 + 30 * 60)
S = 1_000_000_000
MS = 1_000_000
OP = 1000
E1 = Escenario(1, 3, 300, 3)
ARCHIVO_REAL = config.CARPETA_DATA_TICKS / "2026_09_S3_(septiembre_14).txt"


def dia_de(filas, apertura=APERTURA):
    """filas: lista de (ns, precio[, volumen])."""
    tabla = pl.DataFrame(
        {"ns": [f[0] for f in filas], "last": [f[1] for f in filas], "vol": [f[2] if len(f) > 2 else 1 for f in filas]},
        schema={"ns": pl.Int64, "last": pl.Int32, "vol": pl.Int32},
    )
    return crear_dia(tabla, apertura)


def camino(signo, puntos):
    """puntos: (milisegundos tras el cierre, ticks respecto a la orden; positivo = ya pasó la orden a favor)."""
    return dia_de([(HORA - 5 * S, OP + signo * -20)] + [(HORA + ms * MS, OP + signo * d) for ms, d in puntos])


@pytest.fixture
def entrar(senal):
    """Simula con una señal Trend Te 1 (ventana de 2 min, cierre 13:40:00)."""

    def correr(signo, puntos, escenario=E1):
        return simular_entrada(senal(Tipo="Buy" if signo > 0 else "Sell"), camino(signo, puntos), OP, escenario)

    return correr


LADOS = [1, -1]


@pytest.mark.parametrize("signo", LADOS)
def test_colocacion_normal_y_disparo(entrar, signo):
    r = entrar(signo, [(100, -5), (299, -2), (5000, -1), (6000, 0), (6100, 4)])
    assert r.estado == config.EJECUTADA and r.indice == 4  # el tick que llega exactamente a la orden


@pytest.mark.parametrize("signo", LADOS)
def test_disparo_con_tick_mas_alla_de_la_orden(entrar, signo):
    r = entrar(signo, [(100, -5), (6000, 3)])
    assert r.estado == config.EJECUTADA and r.indice == 2


@pytest.mark.parametrize("signo", LADOS)
def test_tocar_la_orden_antes_de_colocar_no_ejecuta(entrar, signo):
    # Antes de los 300 ms el precio la toca, pero vuelve: la orden aún no existía.
    r = entrar(signo, [(100, 0), (200, -5), (6000, -1)])
    assert r.estado == config.NO_EJECUTADA


@pytest.mark.parametrize("signo", LADOS)
def test_precio_igual_a_la_orden_bloquea(entrar, signo):
    r = entrar(signo, [(250, 0), (5000, -3), (9000, 1)])
    assert r.estado == config.EJECUTADA and r.indice == 3


@pytest.mark.parametrize("signo", LADOS)
def test_reintento_espera_la_demora(entrar, signo):
    # Bloqueada a los 300 ms. Vuelve a los 5000 ms; se coloca a los 5300 ms.
    # El toque de los 5100 ms cae antes de colocar y no dispara.
    r = entrar(signo, [(250, 2), (5000, -3), (5100, -1), (5200, -3), (8000, 0)])
    assert r.estado == config.EJECUTADA and r.indice == 5


@pytest.mark.parametrize("signo", LADOS)
def test_reintento_vuelve_a_bloquearse(entrar, signo):
    r = entrar(signo, [(250, 2), (5000, -3), (5200, 4), (9000, -2), (15000, 0)])
    assert r.estado == config.EJECUTADA and r.indice == 5


@pytest.mark.parametrize("signo, maximo, estado", [(1, 45, config.EJECUTADA), (1, 46, config.NO_EJECUTADA_OP), (-1, 45, config.EJECUTADA), (-1, 46, config.NO_EJECUTADA_OP)])
def test_limite_de_45_ticks(entrar, signo, maximo, estado):
    r = entrar(signo, [(250, 2), (2000, maximo), (5000, -3), (9000, 0)])
    assert r.estado == estado


@pytest.mark.parametrize("signo, maximo, estado", [(1, 60, config.EJECUTADA), (1, 61, config.NO_EJECUTADA_OP), (-1, 60, config.EJECUTADA), (-1, 61, config.NO_EJECUTADA_OP)])
def test_limite_de_reentrada_por_escenario(entrar, signo, maximo, estado):
    principal = Escenario(1, 3, 200, 3, 60)
    r = entrar(signo, [(150, 2), (2000, maximo), (5000, -3), (9000, 0)], principal)
    assert r.estado == estado


@pytest.mark.parametrize("signo", LADOS)
def test_bloqueada_sin_regreso(entrar, signo):
    assert entrar(signo, [(250, 2), (5000, 10)]).estado == config.NO_EJECUTADA_OP


@pytest.mark.parametrize("signo", LADOS)
def test_fin_de_ventana_no_incluido(entrar, signo):
    # Trend Te 1: ventana de 2 velas = 120 s desde el cierre.
    assert entrar(signo, [(100, -5), (119_999, 0)]).estado == config.EJECUTADA
    assert entrar(signo, [(100, -5), (120_000, 0)]).estado == config.NO_EJECUTADA


def test_ventana_corta_para_zona_de_impulso(senal):
    s = senal(Zona_Reacción="I. Fuerte")
    d = camino(1, [(100, -5), (59_999, -1), (60_000, 0)])
    assert simular_entrada(s, d, OP, E1).estado == config.NO_EJECUTADA


def test_demora_del_escenario(senal):
    d = camino(1, [(100, -5), (500, 2), (600, -2), (9000, 0)])
    assert simular_entrada(senal(), d, OP, E1).indice == 2  # colocada a 300 ms, dispara a 500 ms
    tardia = Escenario(3, 3, 700, 3)
    assert simular_entrada(senal(), d, OP, tardia).indice == 4  # colocada a 700 ms, dispara a 9000 ms


def test_precio_orden_y_validacion():
    assert precio_orden(100, 1, E1) == 103 and precio_orden(100, -1, E1) == 97
    assert orden_valida(103, 102, 1) and not orden_valida(102, 102, 1)
    assert orden_valida(97, 98, -1) and not orden_valida(98, 98, -1)


def camino_recorrido(puntos):
    return dia_de([(HORA + ms * MS, p) for ms, p in puntos])


def test_mfe_primera_vez_y_mae_pre():
    d = camino_recorrido([(0, 100), (1000, 90), (2000, 130), (3000, 130), (4000, 70), (5000, 110)])
    r = recorridos(d, 0, 100, 1, horizontes=(1,))[1]
    assert (r.mfe, r.mae_pre_mfe, r.mae) == (30, 10, 30)
    assert r.hora_mfe_ns == HORA + 2000 * MS


def test_venta_mide_al_reves():
    d = camino_recorrido([(0, 100), (1000, 110), (2000, 70), (3000, 95)])
    r = recorridos(d, 0, 100, -1, horizontes=(1,))[1]
    assert (r.mfe, r.mae_pre_mfe, r.mae) == (30, 10, 10)


def test_limite_exacto_del_horizonte():
    d = camino_recorrido([(0, 100), (59_999, 105), (60_000, 500)])
    assert recorridos(d, 0, 100, 1, horizontes=(1,))[1].mfe == 5


def test_mfe_negativo_con_deslizamiento():
    d = camino_recorrido([(0, 100), (1000, 99)])
    r = recorridos(d, 0, 103, 1, horizontes=(1,))[1]
    assert r.mfe == -3 and r.mae == 4


def test_e4_es_e1_desplazado():
    d = camino_recorrido([(0, 100), (1000, 90), (2000, 130), (3000, 70)])
    a = recorridos(d, 0, 103, 1, horizontes=(1,))[1]
    b = recorridos(d, 0, 106, 1, horizontes=(1,))[1]
    assert (b.mfe, b.mae, b.mae_pre_mfe, b.hora_mfe_ns) == (a.mfe - 3, a.mae + 3, a.mae_pre_mfe + 3, a.hora_mfe_ns)


def test_tras_ir_a_favor():
    d = camino_recorrido([(0, 100), (1000, 140), (2000, 100), (3000, 160)])
    r = tras_ir_a_favor(d, 0, 100, 1, 40, minutos=1)
    assert r.llega and r.vuelve_a_entrada
    sin_volver = tras_ir_a_favor(camino_recorrido([(0, 100), (1000, 140), (2000, 150)]), 0, 100, 1, 40, minutos=1)
    assert sin_volver.llega and not sin_volver.vuelve_a_entrada and sin_volver.maximo == 50
    assert not tras_ir_a_favor(camino_recorrido([(0, 100), (1000, 120)]), 0, 100, 1, 40, minutos=1).llega


def test_atr_apertura_a_mano():
    m = 60 * S
    d = dia_de([
        (APERTURA, 100), (APERTURA + 30 * S, 110), (APERTURA + m - 1, 105),   # H110 L100 C105: TR 10
        (APERTURA + m, 120), (APERTURA + 2 * m - 1, 115),                     # H120 L115, previo 105: TR 15
    ])
    assert atr_apertura(d, 2) == pytest.approx(12.5)


def test_atr_no_usa_datos_posteriores_a_la_senal():
    m = 60 * S
    base = [(APERTURA, 100), (APERTURA + m - 1, 110), (APERTURA + m, 110), (APERTURA + 2 * m - 1, 120)]
    futuro = base + [(APERTURA + 2 * m, 5000), (APERTURA + 3 * m - 1, 1)]
    hora = APERTURA + 2 * m
    assert atr_hasta(dia_de(base), hora) == atr_hasta(dia_de(futuro), hora)


def test_volumen_primera_hora():
    d = dia_de([(APERTURA - 1, 100, 7), (APERTURA, 100, 2), (APERTURA + 3599 * S, 100, 3), (APERTURA + 3600 * S, 100, 9)])
    assert volumen_primera_hora(d) == 5


def test_lectura_por_porcentaje():
    valores = np.array([10.0, 20.0, 30.0, 40.0])
    assert al_menos(valores, 50) == 30
    assert no_paso_de(valores, 50) == 20
    assert al_menos(valores, 75) == 20
    assert no_paso_de(valores, 75) == 30


@pytest.mark.parametrize("mfe, pre, mae, posicion", [
    (80, 119, 200, 0),   # Positiva: MAE pre < SL y MFE >= TP (límites exactos)
    (79, 120, 200, 1),   # Negativa: MAE pre >= SL y MFE < TP
    (79, 119, 120, 2),   # Negativa tras el máximo
    (79, 119, 119, 3),   # Sin tocar
    (80, 120, 200, 4),   # Dudosa
])
def test_cinco_casos_de_combinacion(mfe, pre, mae, posicion):
    conteo = clasificar(np.array([mfe]), np.array([pre]), np.array([mae]), 120, 80)
    assert conteo == tuple(1 if i == posicion else 0 for i in range(5))


def test_azar_repetible():
    dias = {}
    for k, inicio in enumerate((0, 86_400)):
        o = APERTURA + inicio * S
        dias[f"d{k}"] = dia_de([(o + i * S, 100 + i % 7) for i in range(2000)], apertura=o)
    a = medir_azar([("d0", 10 * S)], dias, 3, semilla=5, por_senal=1)
    b = medir_azar([("d0", 10 * S)], dias, 3, semilla=5, por_senal=1)
    assert np.array_equal(a["mfe"], b["mfe"]) and a["mfe"].shape == (1, 10)


@pytest.fixture(scope="module")
def dia_real(tmp_path_factory):
    if not ARCHIVO_REAL.exists():
        pytest.skip("no está el archivo real del 14-sep")
    data = tmp_path_factory.mktemp("data")
    salida = tmp_path_factory.mktemp("salida")
    (data / ARCHIVO_REAL.name).write_bytes(ARCHIVO_REAL.read_bytes())
    extraer(data, salida, {"20260914": Ventana("132000", "150000")}, avisar=lambda _: None)
    return cargar_dia(ruta_parquet(salida, "20260914"), APERTURA)


def _ns_hora(h, m, s=0.0):
    return ns_del_dia(FECHA, h * 3600 + m * 60) + round(s * 1000) * MS


def test_ejemplo_1_real(senal, dia_real):
    s = senal(Te=1, Zona_Reacción="1er Vela", Tipo="Sell", Hora=time(8, 31), Vela_OP=time(8, 31), Hora_UTC=time(13, 31), Vela_OP_UTC=time(13, 31), OHLC="Low")
    op = round(28882.50 * 4)
    e = simular_entrada(s, dia_real, op, E1)
    assert e.estado == config.EJECUTADA and int(dia_real.ns[e.indice]) == _ns_hora(13, 31, 0.384)
    r = recorridos(dia_real, e.indice, op - 3, -1)[1]
    assert (r.mfe, r.hora_mfe_ns, r.mae_pre_mfe, r.mae) == (5, _ns_hora(13, 31, 1.168), 11, 149)


def test_ejemplo_2_real(senal, dia_real):
    s = senal(Te=2, Zona_Reacción="Trend 1er Pivot", Tipo="Buy", Hora=time(9, 0), Vela_OP=time(9, 0), Hora_UTC=time(14, 0), Vela_OP_UTC=time(14, 0), OHLC="High")
    op = round(29019.75 * 4)
    e = simular_entrada(s, dia_real, op, E1)
    assert int(dia_real.ns[e.indice]) == _ns_hora(14, 0, 48.548)
    r = recorridos(dia_real, e.indice, op + 3, 1)
    assert (r[1].mfe, r[1].mae_pre_mfe, r[1].mae) == (57, 46, 46)
    assert (r[6].mfe, r[6].hora_mfe_ns, r[6].mae_pre_mfe, r[6].mae) == (157, _ns_hora(14, 6, 47.508), 63, 63)
    assert (r[4].mfe, r[4].hora_mfe_ns, r[4].mae_pre_mfe, r[4].mae) == (75, _ns_hora(14, 1, 58.896), 46, 63)
