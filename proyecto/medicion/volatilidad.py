"""ATR de la apertura de NY y volumen de la primera hora.

El ATR de la apertura promedia el True Range de las velas de 1 minuto desde la
apertura, en lugar de mirar solo las últimas 10 velas.
"""

import numpy as np

from medicion.entrada import Dia

_NS_MINUTO = 60_000_000_000
_VELAS_PRIMERA_HORA = 60


def atr_apertura(dia: Dia, velas: int = _VELAS_PRIMERA_HORA) -> float | None:
    """Promedio del True Range de las primeras `velas` velas de 1 minuto, en ticks."""
    bordes = np.searchsorted(dia.ns, [dia.apertura_ns + i * _NS_MINUTO for i in range(velas + 1)])
    rangos = []
    cierre_previo = None
    for a, b in zip(bordes[:-1], bordes[1:]):
        if b <= a:
            continue
        precios = dia.last[int(a):int(b)]
        alto, bajo, cierre = int(precios.max()), int(precios.min()), int(precios[-1])
        referencia = cierre if cierre_previo is None else cierre_previo
        rangos.append(max(alto - bajo, abs(alto - referencia), abs(bajo - referencia)))
        cierre_previo = cierre
    return float(np.mean(rangos)) if rangos else None


def atr_hasta(dia: Dia, hora_ns: int) -> float | None:
    """ATR de la apertura con las velas ya cerradas a la hora indicada; no usa datos posteriores."""
    return atr_apertura(dia, max((hora_ns - dia.apertura_ns) // _NS_MINUTO, 1))


def volumen_primera_hora(dia: Dia) -> int:
    fin = dia.apertura_ns + _VELAS_PRIMERA_HORA * _NS_MINUTO
    return int(dia.vol[np.searchsorted(dia.ns, dia.apertura_ns):np.searchsorted(dia.ns, fin)].sum())
