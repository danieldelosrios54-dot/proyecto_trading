"""Criterios de estado de cada forma (documento 5) y su argumento escrito con números."""

from dataclasses import dataclass

import numpy as np

from simulador.metricas import Calificacion

CANDIDATA = "Candidata a la Matriz principal"
OBSERVACION = "En observación"
DESCARTADA = "Descartada"  # también: requiere 2 cuentas o medición con sesgo
NO_APLICA = "No Aplica"  # no es una decisión, es un costo (por ejemplo, el deslizamiento)
NO_MEDIDA = "No Medida"  # falta un dato para medirla
ESTADOS = (CANDIDATA, OBSERVACION, DESCARTADA, NO_APLICA, NO_MEDIDA)


def umbral(valor_referencia: float) -> float:
    """Mejora material: al menos 100 USD o el 10 % del valor de la referencia."""
    return max(100.0, 0.10 * abs(valor_referencia))


@dataclass
class Evaluacion:
    """Resultado de una forma: dentro y fuera de muestra, resultado semanal fuera y caída máxima."""
    dentro: Calificacion
    fuera: Calificacion
    semanas: np.ndarray  # neto fuera de muestra por semana
    caida: float
    elegida: str = ""
    vecinas: float | None = None
    top: dict | None = None  # resumen de las combinaciones (top 20 por ganancia); None si la forma no tiene tabla de combinaciones


def proporcion_ambas(top: dict | None) -> float | None:
    """De las combinaciones positivas, fracción que gana también en ambas mitades. None si no hay tabla de combinaciones."""
    if top is None or "ambas_todas" not in top:
        return None
    return top["ambas_todas"] / top["positivas"] if top["positivas"] else 0.0


def consistencia(top: dict | None, ref_top: dict | None = None) -> tuple[bool | None, str]:
    """¿La proporción de sus combinaciones positivas que gana en ambas mitades no es menor que la de la referencia?

    None si no hay tabla de combinaciones (o si no se da la referencia).
    """
    p = proporcion_ambas(top)
    if p is None:
        return None, "Sin tabla de combinaciones: el criterio de ambas mitades no aplica."
    if top["positivas"] == 0:
        return False, "Ninguna combinación gana en el total de las 14 semanas."
    texto = f"{top['ambas_todas']:,} de {top['positivas']:,} combinaciones positivas ganan en ambas mitades ({100 * p:.0f} %".replace(",", ".")
    q = proporcion_ambas(ref_top)
    if q is None:
        return None, texto + ")."
    return p >= q - 1e-12, texto + f"; la referencia: {100 * q:.0f} %)."


def diferencia_semanal(a: np.ndarray, b: np.ndarray, repeticiones: int = 10_000, semilla: int = 2026) -> tuple[float, float, float]:
    """Media de la diferencia semana a semana (a − b) y su margen del 95 % remuestreando semanas."""
    d = np.asarray(a, float) - np.asarray(b, float)
    azar = np.random.default_rng(semilla)
    medias = d[azar.integers(0, len(d), (repeticiones, len(d)))].mean(1)
    return float(d.mean()), float(np.quantile(medias, 0.025)), float(np.quantile(medias, 0.975))


def _usd(x: float) -> str:
    return f"{x:+,.0f}".replace(",", ".")


def decidir(ev: Evaluacion, ref: Evaluacion, azar_mediana: float, es_referencia: bool = False) -> tuple[str, str]:
    """(estado, argumento) según los criterios aprobados."""
    f, r = ev.fuera, ref.fuera
    media, bajo, alto = diferencia_semanal(ev.semanas, ref.semanas)
    positiva = f.neto > 0 and f.mitad1 > 0 and f.mitad2 > 0
    supera_azar = f.neto > azar_mediana
    consistente, texto_consistencia = consistencia(ev.top, ref.top)
    claramente_peor = alto < 0
    mejoras = [nombre for nombre, cond in (
        ("neto fuera de muestra", f.neto > r.neto + umbral(r.neto)),
        ("segunda mitad", f.mitad2 > r.mitad2 + umbral(r.mitad2)),
        ("caída máxima", ev.caida < ref.caida - umbral(ref.caida)),
        ("semanas positivas", f.semanas_positivas >= r.semanas_positivas + 1),
    ) if cond]
    datos = (
        f"Fuera de muestra {_usd(f.neto)} USD (PF {f.pf:.2f}, {f.operaciones} operaciones), mitades {_usd(f.mitad1)} / {_usd(f.mitad2)}, "
        f"{f.semanas_positivas} semanas positivas, caída máxima {ev.caida:,.0f} USD. "
        f"Frente a la referencia: diferencia semanal media {_usd(media)} USD (margen {_usd(bajo)} a {_usd(alto)}). "
        f"Mediana del azar {_usd(azar_mediana)} USD."
    ).replace(",", ".") + " " + texto_consistencia
    if f.neto <= 0:
        return DESCARTADA, "Negativa en semanas no vistas. " + datos
    falta = [t for t, c in (
        ("una mitad es negativa", not (f.mitad1 > 0 and f.mitad2 > 0)),
        ("no supera la mediana del azar", not supera_azar),
        ("menos combinaciones positivas que la referencia ganan en ambas mitades: depende más de una época", consistente is False),
    ) if c]
    if es_referencia:
        if not falta:
            return CANDIDATA, "Escenario de referencia: positivo en semanas no vistas y en ambas mitades, mejor que el azar. " + datos
        return OBSERVACION, f"Escenario de referencia, pero {' y '.join(falta)}. " + datos
    if positiva and supera_azar and not (mejoras and not claramente_peor):
        motivo = "empeora con claridad frente a la referencia" if claramente_peor else "no mejora ninguna medida frente a la referencia"
        return DESCARTADA, f"Positiva, pero no da valor: {motivo}. " + datos
    if not falta:
        return CANDIDATA, f"Positiva en semanas no vistas y en ambas mitades, mejor que el azar, y mejora: {', '.join(mejoras)}. " + datos
    return OBSERVACION, f"Positiva en semanas no vistas, pero {' y '.join(falta)}. " + datos
