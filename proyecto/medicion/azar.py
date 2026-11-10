"""Entradas de referencia: mismo minuto de otro día, dirección al azar.

Sirven para separar lo que hace el mercado a esa hora de lo que aporta la señal.
Solo alimentan las columnas de referencia del análisis; no filtran ninguna señal.
"""

import numpy as np

import config
from medicion.entrada import Dia
from medicion.recorrido import recorridos


def medir_azar(
    ejecutadas: list[tuple[str, int]],
    dias: dict[str, Dia],
    deslizamiento: int,
    semilla: int = config.AZAR_SEMILLA,
    por_senal: int = config.AZAR_POR_SENAL,
) -> dict[str, np.ndarray]:
    """Recibe (día de la señal, nanosegundos desde la apertura). Devuelve matrices entradas × horizontes."""
    azar = np.random.default_rng(semilla)
    fechas = sorted(dias)
    filas = []
    for clave, desde_apertura in ejecutadas:
        otras = [f for f in fechas if f != clave]
        for fecha in azar.choice(otras, min(por_senal, len(otras)), replace=False):
            dia = dias[str(fecha)]
            signo = int(azar.choice([1, -1]))
            indice = int(np.searchsorted(dia.ns, dia.apertura_ns + desde_apertura))
            if indice >= len(dia.ns):
                continue
            filas.append(recorridos(dia, indice, int(dia.last[indice]) + signo * deslizamiento, signo))
    return {
        "mfe": np.array([[f[x].mfe for x in config.HORIZONTES] for f in filas]),
        "mae_pre_mfe": np.array([[f[x].mae_pre_mfe for x in config.HORIZONTES] for f in filas]),
        "mae": np.array([[f[x].mae for x in config.HORIZONTES] for f in filas]),
    }
