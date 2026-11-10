from datetime import date, time

import pytest

import config
from validacion.modelos import estado, ns_del_dia
from validacion.ticks import ResultadoFecha, aplicar_t12, estado_fecha, motivos_senal, tramo_ns, validar_dia

FECHA = date(2026, 9, 14)
APERTURA = 13 * 3600 + 30 * 60
INI = ns_del_dia(FECHA, APERTURA - 600)
FIN = ns_del_dia(FECHA, APERTURA + 5400)
S = 1_000_000_000


def correr(tabla_ticks, filas):
    r = ResultadoFecha("20260914", FECHA)
    validar_dia(r, tabla_ticks(filas), INI, FIN)
    return r


def continuos(ultimo=FIN, **extra):
    """Ticks cada 5 s, sin huecos, que cubren toda la ventana."""
    return [{"ns": n, "last": 400, **extra} for n in range(INI, ultimo, 5 * S)] + [{"ns": FIN - 1, "last": 400, **extra}]


def por_regla(r, regla):
    return [i for i in r.incidentes if i.regla == regla]


def test_dia_limpio_no_tiene_incidentes(tabla_ticks):
    r = correr(tabla_ticks, continuos())
    assert r.motivos == [] and r.incidentes == []
    assert estado_fecha(r) == config.VALIDA


def test_t3_tiempo_que_retrocede(tabla_ticks):
    filas = continuos()
    filas[10], filas[11] = filas[11], filas[10]
    r = correr(tabla_ticks, filas)
    assert [m.regla for m in r.motivos] == ["T3"]
    assert estado_fecha(r) == config.INVALIDA


def test_t4_tiempos_iguales_permitidos(tabla_ticks):
    filas = continuos()
    filas.insert(11, dict(filas[10]))
    assert correr(tabla_ticks, filas).motivos == []


@pytest.mark.parametrize("cambio, regla, estado_esperado", [
    ({"no_multiplo": True}, "T5", config.INVALIDA),
    ({"vol_mal": True}, "T6", config.INVALIDA),
    ({"bid": 401, "ask": 400}, "T7", config.NOTIFICADA),
    ({"last": 400, "bid": 401, "ask": 402}, "T8", config.NOTIFICADA),
])
def test_reglas_de_cada_tick(tabla_ticks, cambio, regla, estado_esperado):
    filas = continuos()
    filas[5] = {**filas[5], **cambio}
    r = correr(tabla_ticks, filas)
    assert regla in [m.regla for m in r.motivos]
    assert estado_fecha(r) == estado_esperado


@pytest.mark.parametrize("salto, cuenta", [(60, 0), (61, 1)])
def test_t9_umbral_de_salto(tabla_ticks, salto, cuenta):
    filas = continuos()
    filas[20:] = [{**f, "last": 400 + salto} for f in filas[20:]]
    assert len(por_regla(correr(tabla_ticks, filas), "T9")) == cuenta


def test_t9_guarda_tamano_pausa_y_volumen(tabla_ticks):
    filas = continuos()
    filas[20:] = [{**f, "last": 500} for f in filas[20:]]
    filas[20]["vol"] = 438
    incidente = por_regla(correr(tabla_ticks, filas), "T9")[0]
    assert (incidente.ticks, incidente.pausa_ms, incidente.volumen) == (100, 5000, 438)


def _con_hueco(segundos_ns):
    a = INI + 100 * S
    return [{"ns": n, "last": 400} for n in range(INI, a + 1, 5 * S)] + [
        {"ns": n, "last": 400} for n in range(a + segundos_ns, FIN, 5 * S)
    ] + [{"ns": FIN - 1, "last": 400}]


@pytest.mark.parametrize("hueco_ns, t10, t11", [
    (10 * S - 1_000_000, 0, 0),
    (10 * S, 1, 0),
    (60 * S, 1, 0),
    (60 * S + 1_000_000, 0, 1),
])
def test_umbrales_de_hueco(tabla_ticks, hueco_ns, t10, t11):
    r = correr(tabla_ticks, _con_hueco(hueco_ns))
    assert len(por_regla(r, "T10")) == t10
    assert len(por_regla(r, "T11")) == t11


def test_hueco_al_inicio_de_la_ventana(tabla_ticks):
    filas = [{"ns": n, "last": 400} for n in range(INI + 11 * S, FIN, 5 * S)] + [{"ns": FIN - 1, "last": 400}]
    assert len(por_regla(correr(tabla_ticks, filas), "T10")) == 1


def test_hueco_al_final_de_la_ventana(tabla_ticks):
    filas = [{"ns": n, "last": 400} for n in range(INI, FIN - 61 * S + 1, 5 * S)]
    assert len(por_regla(correr(tabla_ticks, filas), "T11")) == 1


def test_t11_no_invalida_la_fecha_completa(tabla_ticks):
    assert estado_fecha(correr(tabla_ticks, _con_hueco(120 * S))) == config.NOTIFICADA


def test_tramo_impulso_te1(senal):
    s = senal(Zona_Reacción="I. Fuerte", Vela_OP=time(8, 38), Vela_OP_UTC=time(13, 38))
    assert tramo_ns(s) == (ns_del_dia(FECHA, 13 * 3600 + 37 * 60), ns_del_dia(FECHA, 13 * 3600 + 53 * 60))


def test_tramo_continuacion_te2(senal):
    s = senal(Zona_Reacción="Canal", Te=2)
    # Vela OP 13:40 Te 2 abre 13:38; fin = 13:40 + 2 velas de 2 min + 12 min
    assert tramo_ns(s) == (ns_del_dia(FECHA, 13 * 3600 + 38 * 60), ns_del_dia(FECHA, 13 * 3600 + 56 * 60))


def _resultado_con_hueco(tabla_ticks, desde_apertura_min, duracion_s):
    a = ns_del_dia(FECHA, APERTURA + desde_apertura_min * 60)
    filas = [{"ns": n, "last": 400} for n in range(INI, a + 1, 5 * S)]
    filas += [{"ns": n, "last": 400} for n in range(a + duracion_s * S, FIN, 5 * S)] + [{"ns": FIN - 1, "last": 400}]
    return correr(tabla_ticks, filas)


def test_t11_dentro_del_tramo_invalida_la_senal(tabla_ticks, senal):
    # Señal 13:40 Te 1 continuación: tramo 13:39 a 13:54.
    r = _resultado_con_hueco(tabla_ticks, 15, 90)
    assert estado(motivos_senal(senal(), r)) == config.INVALIDA


def test_t11_fuera_del_tramo_no_afecta_la_senal(tabla_ticks, senal):
    r = _resultado_con_hueco(tabla_ticks, 83, 390)
    assert motivos_senal(senal(), r) == []


def test_t10_en_tramo_notifica(tabla_ticks, senal):
    r = _resultado_con_hueco(tabla_ticks, 15, 30)
    assert estado(motivos_senal(senal(), r)) == config.NOTIFICADA


def test_t9_solo_notifica_y_solo_en_tramo(tabla_ticks, senal):
    n_dentro = ns_del_dia(FECHA, 13 * 3600 + 45 * 60)
    filas = continuos()
    i = next(k for k, f in enumerate(filas) if f["ns"] >= n_dentro)
    filas[i:] = [{**f, "last": 500} for f in filas[i:]]
    r = correr(tabla_ticks, filas)
    assert estado(motivos_senal(senal(), r)) == config.NOTIFICADA
    tardia = senal(Hora=time(9, 20), Vela_OP=time(9, 20), Hora_UTC=time(14, 20), Vela_OP_UTC=time(14, 20))
    assert motivos_senal(tardia, r) == []


def test_t2_senal_sin_ventana(senal):
    assert estado(motivos_senal(senal(), None)) == config.INVALIDA


def _dia_con_volumen(clave, volumen):
    return ResultadoFecha(clave, FECHA, ticks=1, volumen=volumen)


def test_t12_umbral_de_volumen():
    resultados = {c: _dia_con_volumen(c, v) for c, v in (("a", 49), ("b", 100), ("c", 100), ("d", 50), ("e", 100))}
    assert aplicar_t12(resultados) == 100
    assert [m.regla for m in resultados["a"].motivos] == ["T12"]
    assert resultados["d"].motivos == []


def test_t12_afecta_a_todas_las_senales_de_la_fecha(senal):
    r = _dia_con_volumen("a", 1)
    aplicar_t12({"a": r, "b": _dia_con_volumen("b", 100), "c": _dia_con_volumen("c", 100)})
    assert estado(motivos_senal(senal(), r)) == config.NOTIFICADA
