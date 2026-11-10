"""Lectura del registro de señales y reglas R1 a R12."""

import warnings
from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

import config
from validacion.modelos import Motivo, Senal

COLUMNAS = [
    "Fecha", "Hora", "Te", "Zona Reacción", "M", "Tipo", "Vela OP",
    "Condiciones Estructura", "Condiciones Continuidad", "SE", "SC", "D",
    "Notas (Duda / C. Fuerte)", "ID", "Hora UTC", "Vela OP UTC", "Apertura UTC", "OHLC",
]
_COLUMNAS_FILA_REAL = ("Fecha", "Hora", "Te", "Tipo", "ID")


def _segundos(valor) -> int | None:
    """Hora de Excel en segundos del día, redondeada al segundo.

    Excel guarda las horas con decimales: comparar sin redondear daría
    diferencias falsas de milésimas.
    """
    if isinstance(valor, datetime):
        valor = valor.time()
    if isinstance(valor, time):
        return round(valor.hour * 3600 + valor.minute * 60 + valor.second + valor.microsecond / 1e6) % 86_400
    if isinstance(valor, timedelta):
        return round(valor.total_seconds()) % 86_400
    return None


def _fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    return valor if isinstance(valor, date) else None


def _entero(valor) -> int | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return int(valor) if float(valor).is_integer() else None


def crear_senal(fila: int, crudo: dict) -> Senal:
    return Senal(
        fila=fila,
        crudo=crudo,
        id=_entero(crudo["ID"]),
        fecha=_fecha(crudo["Fecha"]),
        te=_entero(crudo["Te"]),
        zona=crudo["Zona Reacción"],
        tipo=crudo["Tipo"],
        ohlc=crudo["OHLC"],
        hora_s=_segundos(crudo["Hora"]),
        vela_op_s=_segundos(crudo["Vela OP"]),
        hora_utc_s=_segundos(crudo["Hora UTC"]),
        vela_op_utc_s=_segundos(crudo["Vela OP UTC"]),
        apertura_s=_segundos(crudo["Apertura UTC"]),
    )


def leer_registro(ruta: Path) -> tuple[list[Senal], set[str], set[str]]:
    """Devuelve las señales y las condiciones de estructura y continuidad permitidas."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # aviso inofensivo de la tabla dinámica de "Conteo"
        libro = openpyxl.load_workbook(ruta, data_only=True)

    hoja = libro[config.HOJA_REGISTRO]
    encabezados = [
        c.strip() if isinstance(c, str) else c
        for c in next(hoja.iter_rows(min_row=config.FILA_ENCABEZADOS, max_row=config.FILA_ENCABEZADOS, values_only=True))
    ]
    faltantes = [c for c in COLUMNAS if c not in encabezados]
    if faltantes:
        raise ValueError(f"Faltan columnas en '{config.HOJA_REGISTRO}': {', '.join(faltantes)}")

    senales = []
    for numero, valores in enumerate(hoja.iter_rows(min_row=config.FILA_ENCABEZADOS + 1, values_only=True), config.FILA_ENCABEZADOS + 1):
        crudo = dict(zip(encabezados, valores))
        if any(crudo[c] is not None for c in _COLUMNAS_FILA_REAL):
            senales.append(crear_senal(numero, crudo))

    condiciones = {
        celda.strip()
        for fila in libro[config.HOJA_CONDICIONES].iter_rows(values_only=True)
        for celda in fila
        if isinstance(celda, str)
    }
    estructura = {c for c in condiciones if c.startswith("E - ")}
    continuidad = {c for c in condiciones if c.startswith("C - ")}
    return senales, estructura, continuidad


def apertura_esperada_s(fecha: date) -> int:
    """Hora UTC, en segundos, de las 9:30 de Nueva York en esa fecha."""
    local = datetime.combine(fecha, time(9, 30), ZoneInfo(config.ZONA_HORARIA_NY))
    utc = local.astimezone(timezone.utc)
    return utc.hour * 3600 + utc.minute * 60


def _invalidar(regla: str, texto: str) -> Motivo:
    return Motivo(regla, config.INVALIDAR, texto)


def _en(valor, permitidos) -> bool:
    return isinstance(valor, str) and valor in permitidos


def _reglas_senal(s: Senal, repetidas: Counter, ids: Counter, cond_e: set[str], cond_c: set[str]) -> Iterator[Motivo]:
    # R1
    clave = (s.fecha, s.te, s.hora_utc_s)
    if None not in clave and repetidas[clave] > 1:
        yield _invalidar("R1", "otra fila tiene la misma Fecha, Te y Hora UTC")

    # R2
    if s.fecha is None:
        yield _invalidar("R2", "Fecha vacía o no válida")
    elif s.fecha.weekday() > 4:
        yield _invalidar("R2", f"{s.fecha} no es de lunes a viernes")

    # R3
    if s.te not in config.VALORES_TE:
        yield _invalidar("R3", f"Te no permitido: {s.crudo['Te']!r}")
    if not _en(s.zona, config.ZONAS):
        yield _invalidar("R3", f"Zona Reacción no permitida: {s.zona!r}")
    if not _en(s.tipo, config.VALORES_TIPO):
        yield _invalidar("R3", f"Tipo no permitido: {s.tipo!r}")
    if s.apertura_s not in config.APERTURAS_UTC_S:
        yield _invalidar("R3", f"Apertura UTC no permitida: {s.crudo['Apertura UTC']!r}")
    if not _en(s.ohlc, config.VALORES_OHLC):
        yield _invalidar("R3", f"OHLC no permitido: {s.ohlc!r}")

    # R4
    notas = s.crudo["Notas (Duda / C. Fuerte)"]
    r4 = [
        ("M", s.crudo["M"], config.VALORES_M),
        ("Condiciones Estructura", s.crudo["Condiciones Estructura"], {"-"} | cond_e),
        ("Condiciones Continuidad", s.crudo["Condiciones Continuidad"], {"-"} | cond_c),
        ("SE", s.crudo["SE"], config.VALORES_ESTATUS),
        ("SC", s.crudo["SC"], config.VALORES_ESTATUS),
        ("D", s.crudo["D"], config.VALORES_D),
    ]
    for columna, valor, permitidos in r4:
        texto = valor.strip() if isinstance(valor, str) else valor
        if not _en(texto, permitidos):
            yield Motivo("R4", config.NOTIFICAR, f"{columna} vacía o no permitida: {valor!r}")
    if notas is None or (isinstance(notas, str) and not notas.strip()):
        yield Motivo("R4", config.NOTIFICAR, "Notas vacía")

    # R5 y R6
    desfase = config.HORAS_COLOMBIA_A_UTC * 3600
    for regla, local, utc, nombre in (
        ("R5", s.hora_s, s.hora_utc_s, "Hora"),
        ("R6", s.vela_op_s, s.vela_op_utc_s, "Vela OP"),
    ):
        if local is None or utc is None:
            yield _invalidar(regla, f"{nombre} o {nombre} UTC vacía o no es una hora")
        elif (local + desfase) % 86_400 != utc:
            yield _invalidar(regla, f"{nombre} + 5 h no coincide con {nombre} UTC")

    # R7
    if s.id is None:
        yield _invalidar("R7", "ID vacío o no numérico")
    elif ids[s.id] > 1:
        yield _invalidar("R7", f"ID {s.id} repetido")

    # R8
    if s.te in config.VALORES_TE and s.hora_utc_s is not None and s.apertura_s is not None:
        desde_apertura = s.hora_utc_s - s.apertura_s
        if not s.te * 60 <= desde_apertura <= 3600:
            yield _invalidar("R8", "Hora UTC fuera de la sesión")
        if s.te == 2 and (s.hora_utc_s // 60) % 2:
            yield _invalidar("R8", "en Te 2 la Hora UTC debe ser minuto par")

    # R9
    if s.hora_utc_s is not None and s.vela_op_utc_s is not None:
        diferencia = s.hora_utc_s - s.vela_op_utc_s
        if diferencia < 0:
            yield _invalidar("R9", "Vela OP UTC es posterior a Hora UTC")
        if s.te == 2 and (s.vela_op_utc_s // 60) % 2:
            yield _invalidar("R9", "en Te 2 la Vela OP UTC debe ser minuto par")
        if s.te in config.VALORES_TE:
            velas_max = None
            if _en(s.zona, config.ZONAS_IMPULSO):
                velas_max = config.VELAS_MAX_OP_IMPULSO
            elif _en(s.zona, config.ZONAS_CONTINUACION):
                velas_max = config.VELAS_MAX_OP_CONTINUACION
            if velas_max is not None and diferencia > velas_max * s.te * 60:
                yield _invalidar("R9", f"Vela OP UTC está a más de {velas_max * s.te} min de Hora UTC")

    # R10
    if _en(s.zona, config.ZONAS) and _en(s.tipo, config.VALORES_TIPO) and _en(s.ohlc, config.VALORES_OHLC):
        esperado = "Close" if s.zona == config.ZONA_VC else ("High" if s.tipo == "Buy" else "Low")
        if s.ohlc != esperado:
            yield _invalidar("R10", f"OHLC debe ser {esperado}, tiene {s.ohlc}")

    # R11
    if _en(s.zona, config.ZONAS_PRIMERA_VELA) and s.te in config.VALORES_TE and s.apertura_s is not None:
        cierre = s.apertura_s + s.te * 60
        if s.hora_utc_s != cierre or s.vela_op_utc_s != cierre:
            yield _invalidar("R11", "Hora UTC y Vela OP UTC deben ser el cierre de la primera vela")

    # R12
    if s.fecha is not None and s.apertura_s is not None:
        if s.apertura_s != apertura_esperada_s(s.fecha):
            yield _invalidar("R12", "Apertura UTC no corresponde a las 9:30 de Nueva York de esa fecha")


def validar_registro(senales: list[Senal], cond_e: set[str], cond_c: set[str]) -> dict[int, list[Motivo]]:
    """Motivos R1 a R12 por fila de Excel."""
    repetidas = Counter((s.fecha, s.te, s.hora_utc_s) for s in senales)
    ids = Counter(s.id for s in senales if s.id is not None)
    return {s.fila: list(_reglas_senal(s, repetidas, ids, cond_e, cond_c)) for s in senales}
