"""Pestaña "Guía de grupos y escenarios"."""

import numpy as np

from simulador import metricas as mt
from simulador.estado_formas import CANDIDATA, DESCARTADA, Evaluacion
from simulador.formas import Fila
from simulador.formas_principal import _RECORRIDO
from simulador.reportes import Resaltado
from simulador.resumen_escenarios import (GRUPO_REFERENCIA, GRUPO_SIN_TREND_V, cambio_mapa, guia_encabezados, pasos_escenario,
                                          que_cambia, que_es_grupo, que_varia, tablas)

REF = dict(_RECORRIDO)


def test_pasos_de_un_escenario_del_mapa():
    cambio = cambio_mapa(5, 100, 8, "Todas")
    pasos = {paso: (valor, cambia) for paso, valor, cambia in pasos_escenario(cambio)}
    assert pasos["Calcular el precio de la orden pendiente"] == ('"OHLC" ± 5 ticks', True)
    assert pasos["Colocación de la orden pendiente"] == ("00:00:00.100", True)
    assert pasos["Cierre por tiempo"] == ("8 minutos desde la entrada", True)
    assert pasos["ATM"] == (REF["ATM"], False) and pasos["Selección"] == (REF["Selección"], False)
    assert cambio_mapa(3, 200, 9, "Todas") == {}  # la fila del mapa igual a la referencia no cambia nada
    assert cambio_mapa(3, 200, 9, "Sin Trend ≥ 2do Pivot ni V") == {"Selección": "Sin Trend ≥ 2do Pivot ni V"}


def test_que_varia_y_que_cambia():
    assert que_varia([cambio_mapa(3, 200, 9, "Todas"), cambio_mapa(5, 200, 8, "Todas")]) == (
        'Calcular el precio de la orden pendiente: "OHLC" ± 3 ticks / "OHLC" ± 5 ticks; Cierre por tiempo: 8 minutos desde la entrada / 9 minutos desde la entrada')
    assert que_varia([{}]) == "Un solo escenario."
    assert que_cambia({}) == "Nada: usa el mismo Recorrido que la referencia."
    assert que_cambia({"Gestión": "Breakeven en +30 USD"}) == f"Gestión: Breakeven en +30 USD (referencia: {REF['Gestión']})"


def test_textos_de_los_grupos():
    assert "Zona Reacción Canal" in que_es_grupo("Dejar de operar Canal")
    assert "columna M" in que_es_grupo("Dejar de operar con estructura M = LA")
    assert "ADX (14)" in que_es_grupo("No operar el tercio de ADX (14) que perdió en las otras semanas")
    assert "ATR (10)" in que_es_grupo("ATM según tercio de ATR (10)")
    for nombre in (GRUPO_REFERENCIA, GRUPO_SIN_TREND_V, "Corte temprano", "Breakeven", "Stop al cierre de vela", "Deslizamiento de entrada"):
        assert que_es_grupo(nombre)
    assert que_es_grupo("Algo nuevo sin texto") is None


def test_pestana_guia_un_escenario_por_fila_con_los_mismos_nombres():
    cal = mt.Calificacion(100.0, 10, 1.2, 8, 50.0, 50.0, ())
    ev = Evaluacion(cal, cal, np.zeros(14), 1.0)
    filas = [
        Fila("1", "Salida", "ATM fijo (referencia)", ev, estado=CANDIDATA, argumento="Escenario de referencia."),
        Fila("1", "Salida", "Breakeven en +60 ticks (30 USD)", ev, estado=DESCARTADA, argumento="Negativa.", cambio={"Gestión": "Breakeven en +30 USD"}),
    ]
    mapa = [(5, 100, 8, "Todas", ev, CANDIDATA, "Positiva.")]
    avisos = []
    pestanas = tablas(filas, mapa, 100.0, avisar=avisos.append)
    resumen, guia = pestanas[0], pestanas[3]
    assert guia.titulo == "Guía de grupos y escenarios" and guia.encabezados == guia_encabezados()
    assert sorted(f[3] for f in guia.filas) == sorted(f[1] for f in resumen.filas)
    por_escenario = {f[3]: f for f in guia.filas}
    referencia = por_escenario["ATM fijo (referencia)"]
    assert referencia[0] == GRUPO_REFERENCIA and not any(isinstance(v, Resaltado) for v in referencia)
    mapa_fila = por_escenario["Mapa: ±5 ticks · 100 ms · 8 min · Todas"]
    assert mapa_fila[0] == GRUPO_REFERENCIA and sum(isinstance(v, Resaltado) for v in mapa_fila) == 3
    breakeven = por_escenario["Breakeven en +60 ticks (30 USD)"]
    gestion = guia.encabezados.index("Gestión")
    assert isinstance(breakeven[gestion], Resaltado) and breakeven[gestion] == "Breakeven en +30 USD"
    assert avisos == []  # todos los grupos tienen su explicación
