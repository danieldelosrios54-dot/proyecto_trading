from datetime import datetime, time

import pytest

import config
from validacion.modelos import estado
from validacion.registro import validar_registro

COND_E = {"E - Medicion"}
COND_C = {"C - Ejecucion"}


def reglas(*senales):
    motivos = validar_registro(list(senales), COND_E, COND_C)
    return {m.regla: m.accion for lista in motivos.values() for m in lista}


def test_senal_correcta_es_valida(senal):
    motivos = validar_registro([senal()], COND_E, COND_C)
    assert estado(motivos[3]) == config.VALIDA


def test_r1_invalida_todas_las_repetidas(senal):
    a, b = senal(fila=3, ID=1), senal(fila=4, ID=2)
    motivos = validar_registro([a, b], COND_E, COND_C)
    assert estado(motivos[3]) == estado(motivos[4]) == config.INVALIDA
    assert {m.regla for m in motivos[3]} == {"R1"}


def test_r1_no_marca_misma_hora_en_otra_temporalidad(senal):
    a = senal(fila=3, ID=1)
    b = senal(fila=4, ID=2, Te=2, **{"Hora": time(8, 40)})
    assert "R1" not in reglas(a, b)


def test_r7_id_repetido_y_vacio(senal):
    assert "R7" in reglas(senal(fila=3, ID=5, Hora_UTC=time(13, 40)), senal(fila=4, ID=5, Hora=time(8, 41), Vela_OP=time(8, 41), Hora_UTC=time(13, 41), Vela_OP_UTC=time(13, 41)))
    assert "R7" in reglas(senal(ID=None))


@pytest.mark.parametrize("cambios, regla, accion", [
    ({"Fecha": datetime(2026, 9, 12)}, "R2", config.INVALIDAR),
    ({"Fecha": "ayer"}, "R2", config.INVALIDAR),
    ({"Te": 3}, "R3", config.INVALIDAR),
    ({"Zona_Reacción": "Otra"}, "R3", config.INVALIDAR),
    ({"Tipo": "Comprar"}, "R3", config.INVALIDAR),
    ({"Apertura_UTC": time(12, 30)}, "R3", config.INVALIDAR),
    ({"OHLC": "Open"}, "R3", config.INVALIDAR),
    ({"M": "X"}, "R4", config.NOTIFICAR),
    ({"Condiciones_Estructura": None}, "R4", config.NOTIFICAR),
    ({"SE": "XX"}, "R4", config.NOTIFICAR),
    ({"D": None}, "R4", config.NOTIFICAR),
    ({"Notas_(Duda_/_C._Fuerte)": None}, "R4", config.NOTIFICAR),
    ({"Hora_UTC": time(13, 41), "Vela_OP_UTC": time(13, 41)}, "R5", config.INVALIDAR),
    ({"Vela_OP_UTC": time(13, 39)}, "R6", config.INVALIDAR),
])
def test_reglas_incumplidas(senal, cambios, regla, accion):
    resultado = reglas(senal(**cambios))
    assert resultado.get(regla) == accion


def test_r4_acepta_condicion_de_la_pestana(senal):
    assert "R4" not in reglas(senal(Condiciones_Estructura=" E - Medicion ", Condiciones_Continuidad="C - Ejecucion", SE="CL", SC="CF", D="D"))


def test_r5_compara_al_segundo_sin_falsos_errores(senal):
    assert "R5" not in reglas(senal(Hora_UTC=time(13, 39, 59, 999999)))


def _a_la_hora(senal, utc_min, te=1, **cambios):
    h, m = divmod(utc_min, 60)
    local, utc = time(h - 5, m), time(h, m)
    datos = {"Hora": local, "Vela_OP": local, "Hora_UTC": utc, "Vela_OP_UTC": utc, "Te": te}
    datos.update(cambios)
    return senal(**datos)


APERTURA = 13 * 60 + 30


@pytest.mark.parametrize("minutos, te, valido", [
    (1, 1, True), (0, 1, False), (60, 1, True), (61, 1, False),
    (2, 2, True), (1, 2, False), (60, 2, True), (62, 2, False),
])
def test_r8_limites_de_sesion(senal, minutos, te, valido):
    assert ("R8" not in reglas(_a_la_hora(senal, APERTURA + minutos, te))) is valido


def test_r8_te2_minuto_impar(senal):
    assert "R8" in reglas(_a_la_hora(senal, APERTURA + 11, 2))


def test_r9_vela_op_posterior(senal):
    assert "R9" in reglas(senal(Vela_OP=time(8, 41), Vela_OP_UTC=time(13, 41)))


def test_r9_te2_vela_op_impar(senal):
    assert "R9" in reglas(_a_la_hora(senal, APERTURA + 10, 2, Vela_OP=time(8, 39), Vela_OP_UTC=time(13, 39)))


@pytest.mark.parametrize("zona, atras, te, valido", [
    ("I. Fuerte", 3, 1, True), ("I. Fuerte", 4, 1, False),
    ("V", 6, 2, True), ("V", 8, 2, False),
    ("Canal", 1, 1, True), ("Canal", 2, 1, False),
    ("Rango", 2, 2, True), ("Rango", 4, 2, False),
])
def test_r9_distancia_maxima(senal, zona, atras, te, valido):
    utc = APERTURA + 20
    h, m = divmod(utc - atras, 60)
    s = _a_la_hora(senal, utc, te, Zona_Reacción=zona, Vela_OP=time(h - 5, m), Vela_OP_UTC=time(h, m))
    assert ("R9" not in reglas(s)) is valido


@pytest.mark.parametrize("zona, tipo, ohlc, valido", [
    ("Canal", "Buy", "High", True), ("Canal", "Buy", "Low", False),
    ("Canal", "Sell", "Low", True), ("Canal", "Sell", "High", False),
    ("Canal", "Buy", "Close", False),
    ("1er Vela (VC)", "Buy", "Close", True), ("1er Vela (VC)", "Buy", "High", False),
])
def test_r10(senal, zona, tipo, ohlc, valido):
    assert ("R10" not in reglas(senal(Zona_Reacción=zona, Tipo=tipo, OHLC=ohlc))) is valido


def test_r11_primera_vela(senal):
    assert "R11" not in reglas(_a_la_hora(senal, APERTURA + 1, 1, Zona_Reacción="1er Vela"))
    assert "R11" not in reglas(_a_la_hora(senal, APERTURA + 2, 2, Zona_Reacción="1er Vela"))
    assert "R11" in reglas(_a_la_hora(senal, APERTURA + 2, 1, Zona_Reacción="1er Vela"))


def test_r12_cambio_de_horario(senal):
    # El 2-nov-2026 Nueva York ya salió del horario de verano: la apertura es 14:30 UTC.
    invierno = dict(Fecha=datetime(2026, 11, 2), Hora=time(9, 40), Vela_OP=time(9, 40), Hora_UTC=time(14, 40), Vela_OP_UTC=time(14, 40))
    assert "R12" not in reglas(senal(Apertura_UTC=time(14, 30), **invierno))
    assert "R12" in reglas(senal(Apertura_UTC=time(13, 30), **invierno))
    assert "R12" not in reglas(senal())
    assert "R12" in reglas(senal(Apertura_UTC=time(14, 30)))
