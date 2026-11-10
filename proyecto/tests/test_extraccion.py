import os

import polars as pl
import pytest

import config
from main import _motivos_t1_t2_t3
from tests.conftest import linea_tick
from validacion.extraccion import Ventana, extraer, ruta_parquet

VENTANAS = {"20260914": Ventana("132000", "150000")}


@pytest.fixture
def carpetas(tmp_path):
    data, salida = tmp_path / "data", tmp_path / "salida"
    data.mkdir()
    return data, salida


def escribir(carpeta, nombre, lineas):
    (carpeta / nombre).write_text("\n".join(lineas) + "\n", encoding="utf-8")


def correr(data, salida, ventanas=VENTANAS):
    return extraer(data, salida, ventanas, avisar=lambda _: None)


def leer(salida, clave="20260914"):
    return pl.read_parquet(ruta_parquet(salida, clave))


def test_bordes_de_la_ventana(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [
        linea_tick(hms="131959", fraccion="9990000", last="1"),
        linea_tick(hms="132000", fraccion="0000000", last="2"),
        linea_tick(hms="145959", fraccion="9990000", last="3"),
        linea_tick(hms="150000", fraccion="0000000", last="4"),
    ])
    correr(data, salida)
    assert leer(salida)["last"].to_list() == [8, 12]


def test_ticks_identicos_se_conservan_y_el_orden_no_cambia(carpetas):
    data, salida = carpetas
    precios = ["100", "100", "99.75", "100.25", "100"]
    escribir(data, "a.txt", [linea_tick(hms="133000", fraccion="1000000", last=p) for p in precios])
    correr(data, salida)
    dia = leer(salida)
    assert dia["last"].to_list() == [400, 400, 399, 401, 400]
    assert dia["pos"].to_list() == [1, 2, 3, 4, 5]


def test_tiempo_en_nanosegundos_enteros_sin_recorte(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick(hms="133000", fraccion="1234567", last="100")])
    correr(data, salida)
    # 2026-09-14 13:30:00 UTC = 1789392600 s desde 1970
    assert leer(salida)["ns"][0] == 1789392600 * 1_000_000_000 + 1234567 * 100


def test_precios_sin_decimales_y_con_decimales(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [
        linea_tick(last="29016", bid="29015.75", ask="29016.5", vol="3"),
    ])
    correr(data, salida)
    fila = leer(salida).row(0, named=True)
    assert (fila["last"], fila["bid"], fila["ask"], fila["vol"]) == (116064, 116063, 116066, 3)
    assert not fila["precio_no_multiplo"] and not fila["volumen_invalido"]


def test_marca_precio_y_volumen_incorrectos_sin_perder_el_tick(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [
        linea_tick(last="100.1"),
        linea_tick(last="100", vol="0"),
        linea_tick(last="100", vol="1.5"),
    ])
    correr(data, salida)
    dia = leer(salida)
    assert dia["precio_no_multiplo"].to_list() == [True, False, False]
    assert dia["volumen_invalido"].to_list() == [False, True, True]


def test_archivo_sin_cambios_no_se_vuelve_a_extraer(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick()])
    _, primero = correr(data, salida)
    _, segundo = correr(data, salida)
    assert primero == ["a.txt"]
    assert segundo == []


def test_archivo_modificado_se_vuelve_a_extraer_y_el_otro_no(carpetas):
    data, salida = carpetas
    ventanas = {**VENTANAS, "20260915": Ventana("132000", "150000")}
    escribir(data, "a.txt", [linea_tick(last="100")])
    escribir(data, "b.txt", [linea_tick(fecha="20260915", last="200")])
    correr(data, salida, ventanas)
    escribir(data, "a.txt", [linea_tick(last="101"), linea_tick(hms="133001", last="102")])
    os.utime(data / "a.txt", ns=(1, 1))
    _, procesados = correr(data, salida, ventanas)
    assert procesados == ["a.txt"]
    assert leer(salida)["last"].to_list() == [404, 408]


def test_ventana_nueva_obliga_a_extraer(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick(), linea_tick(fecha="20260915")])
    correr(data, salida)
    _, procesados = correr(data, salida, {**VENTANAS, "20260915": Ventana("132000", "150000")})
    assert procesados == ["a.txt"]
    assert ruta_parquet(salida, "20260915").exists()


def test_fecha_repartida_entre_archivos_se_ubica_por_la_hora(carpetas):
    data, salida = carpetas
    ventanas = {"20260915": Ventana("132000", "150000")}
    escribir(data, "a.txt", [linea_tick(fecha="20260915", hms="045958", last="100")])
    escribir(data, "b.txt", [linea_tick(fecha="20260915", hms="133000", last="200")])
    registro, _ = correr(data, salida, ventanas)
    assert leer(salida, "20260915")["last"].to_list() == [800]
    assert _motivos_t1_t2_t3("20260915", registro["archivos"]) == []


def test_t3_misma_ventana_en_dos_archivos(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick(last="100")])
    escribir(data, "b.txt", [linea_tick(last="100")])
    registro, _ = correr(data, salida)
    assert [m.regla for m in _motivos_t1_t2_t3("20260914", registro["archivos"])] == ["T3"]


def test_t2_fecha_sin_ticks(carpetas):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick(hms="050000")])
    registro, _ = correr(data, salida)
    assert [m.regla for m in _motivos_t1_t2_t3("20260914", registro["archivos"])] == ["T2"]


@pytest.mark.parametrize("mala, invalida", [
    ("20260914 133000 0000000;100;100;100", True),          # hora legible, dentro de la ventana
    ("20260914 050000 0000000;100;100", False),             # hora legible, fuera de la ventana
    ("20260914 99XX00 basura", True),                       # sin hora legible: toda la fecha
    ("basura total", True),                                 # sin fecha legible: todas las fechas del archivo
])
def test_t1_alcance_de_una_linea_mala(carpetas, mala, invalida):
    data, salida = carpetas
    escribir(data, "a.txt", [linea_tick(), mala])
    registro, _ = correr(data, salida)
    reglas = [m.regla for m in _motivos_t1_t2_t3("20260914", registro["archivos"])]
    assert ("T1" in reglas) is invalida
    assert all(m.accion == config.INVALIDAR for m in _motivos_t1_t2_t3("20260914", registro["archivos"]))
