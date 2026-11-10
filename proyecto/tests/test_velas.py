"""Velas contra los valores reales del Data Box de NinjaTrader y regla R13."""

from datetime import date, time

import polars as pl
import pytest

import config
from validacion.extraccion import Ventana, extraer, ruta_parquet
from validacion.modelos import ns_del_dia
from validacion.velas import armar_vela, regla_r13

FECHA = date(2026, 9, 14)
ARCHIVO_REAL = config.CARPETA_DATA_TICKS / "2026_09_S3_(septiembre_14).txt"
S = 1_000_000_000


def _ns(h, m, s=0.0):
    return ns_del_dia(FECHA, h * 3600 + m * 60) + round(s * 1000) * 1_000_000


@pytest.fixture(scope="module")
def ticks_reales(tmp_path_factory):
    if not ARCHIVO_REAL.exists():
        pytest.skip("no está el archivo real del 14-sep")
    data = tmp_path_factory.mktemp("data")
    salida = tmp_path_factory.mktemp("salida")
    (data / ARCHIVO_REAL.name).write_bytes(ARCHIVO_REAL.read_bytes())
    extraer(data, salida, {"20260914": Ventana("132000", "150000")}, avisar=lambda _: None)
    return pl.read_parquet(ruta_parquet(salida, "20260914"))


@pytest.mark.parametrize("h, m, te, abre, alto, bajo, cierra, volumen", [
    (13, 31, 1, 28905.75, 28924.00, 28883.25, 28885.75, 6518),
    (13, 32, 2, 28905.75, 28924.00, 28880.50, 28898.00, 12333),
    (13, 42, 2, 28888.50, 28914.75, 28882.75, 28910.75, 6916),
    (13, 48, 2, 28967.75, 29003.00, 28967.75, 29003.00, 10614),
    (14, 15, 1, 29073.50, 29081.25, 29071.50, 29073.25, 1740),
    (14, 28, 1, 28985.50, 28998.25, 28983.00, 28996.25, 3240),
])
def test_velas_iguales_al_data_box(ticks_reales, h, m, te, abre, alto, bajo, cierra, volumen):
    vela = armar_vela(ticks_reales, _ns(h, m), te)
    assert (vela.open, vela.high, vela.low, vela.close) == tuple(round(p * 4) for p in (abre, alto, bajo, cierra))
    assert vela.volumen == volumen


@pytest.mark.parametrize("precio, h, m, s, objetivo, h2, m2, s2, ticks, segundos", [
    (28943.50, 13, 43, 38.716, 28978.75, 13, 46, 13.516, 141, 154.8),
    (29063.75, 14, 6, 53.532, 28977.75, 14, 26, 39.284, -344, 1185.752),
])
def test_mediciones_reales(ticks_reales, precio, h, m, s, objetivo, h2, m2, s2, ticks, segundos):
    inicio = ticks_reales.filter((pl.col("ns") == _ns(h, m, s)) & (pl.col("last") == round(precio * 4)))
    assert inicio.height >= 1
    desde_pos = inicio["pos"][0]
    llegada = ticks_reales.filter((pl.col("pos") > desde_pos) & (pl.col("last") == round(objetivo * 4))).row(0, named=True)
    assert llegada["ns"] == _ns(h2, m2, s2)
    assert llegada["last"] - round(precio * 4) == ticks
    assert (llegada["ns"] - _ns(h, m, s)) / S == pytest.approx(segundos)


def test_tick_exacto_en_el_cierre_es_de_la_vela_siguiente(tabla_ticks):
    cierre = _ns(13, 40)
    ticks = tabla_ticks([
        {"ns": cierre - 60 * S, "last": 100},
        {"ns": cierre - 1, "last": 110},
        {"ns": cierre, "last": 999},
    ])
    vela = armar_vela(ticks, cierre, 1)
    assert (vela.high, vela.close, vela.volumen) == (110, 110, 2)
    assert armar_vela(ticks, cierre + 60 * S, 1).open == 999


def test_open_y_close_respetan_el_orden_del_archivo(tabla_ticks):
    cierre = _ns(13, 40)
    mismo = cierre - 30 * S
    vela = armar_vela(tabla_ticks([{"ns": mismo, "last": 105}, {"ns": mismo, "last": 95}, {"ns": mismo, "last": 100}]), cierre, 1)
    assert (vela.open, vela.close, vela.high, vela.low) == (105, 100, 105, 95)


def test_vela_sin_ticks(tabla_ticks):
    assert armar_vela(tabla_ticks([{"ns": _ns(13, 45), "last": 100}]), _ns(13, 40), 1) is None


def _vela(tabla_ticks, abre, cierra):
    return tabla_ticks([{"ns": _ns(13, 39, 10), "last": abre}, {"ns": _ns(13, 39, 50), "last": cierra}])


@pytest.mark.parametrize("tipo, abre, cierra, accion", [
    ("Buy", 100, 110, None),
    ("Buy", 110, 100, config.INVALIDAR),
    ("Sell", 110, 100, None),
    ("Sell", 100, 110, config.INVALIDAR),
    ("Buy", 100, 100, config.NOTIFICAR),
    ("Sell", 100, 100, config.NOTIFICAR),
])
def test_r13_color_de_la_vela(tabla_ticks, senal, tipo, abre, cierra, accion):
    motivos = regla_r13(senal(Tipo=tipo), _vela(tabla_ticks, abre, cierra))
    assert [m.accion for m in motivos] == ([accion] if accion else [])


@pytest.mark.parametrize("abre, cierra", [(100, 110), (110, 100), (100, 100)])
def test_r13_1er_vela_vc_acepta_cualquier_color(tabla_ticks, senal, abre, cierra):
    assert regla_r13(senal(Zona_Reacción="1er Vela (VC)", Tipo="Buy"), _vela(tabla_ticks, abre, cierra)) == []
