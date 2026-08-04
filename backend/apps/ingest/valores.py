"""Conversion de celdas del CSV.

Regla del modelo (ADR-064, seccion 5): un campo vacio es un dato que AnyLogic **no produce**,
nunca un cero implicito. Por eso todas las conversiones devuelven None ante un vacio y el
importador guarda None, no 0.
"""

from __future__ import annotations

VERDADEROS = {"true", "1", "si", "sí", "yes", "t"}
FALSOS = {"false", "0", "no", "n", "f"}


def texto(valor: str | None) -> str:
    return (valor or "").strip()


def flotante(valor: str | None) -> float | None:
    v = texto(valor)
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def entero(valor: str | None) -> int | None:
    v = texto(valor)
    if v == "":
        return None
    try:
        return int(v)
    except ValueError:
        f = flotante(v)
        return None if f is None else int(f)


def booleano(valor: str | None) -> bool | None:
    v = texto(valor).lower()
    if v == "":
        return None
    if v in VERDADEROS:
        return True
    if v in FALSOS:
        return False
    return None
