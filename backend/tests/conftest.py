import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "datos_ejemplo"))

from generar_ejemplo import ARCHIVOS, RUN_ID, escribir  # noqa: E402


@pytest.fixture(scope="session")
def carpeta_ejemplo(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("datos_ejemplo") / RUN_ID
    escribir(destino)
    return destino


def empaquetar(carpeta: Path, cambios: dict[str, bytes] | None = None,
               quitar: tuple[str, ...] = ()) -> bytes:
    """Arma el zip del paquete permitiendo alterar archivos, para probar los rechazos."""
    cambios = cambios or {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in sorted(carpeta.iterdir()):
            if archivo.name in quitar:
                continue
            zf.writestr(archivo.name, cambios.get(archivo.name, archivo.read_bytes()))
        for nombre, contenido in cambios.items():
            if not (carpeta / nombre).exists():
                zf.writestr(nombre, contenido)
    return buffer.getvalue()


@pytest.fixture
def paquete(carpeta_ejemplo) -> bytes:
    return empaquetar(carpeta_ejemplo)


@pytest.fixture
def kpis_barrido(carpeta_ejemplo) -> bytes:
    return (carpeta_ejemplo.parent / "kpis_por_corrida.csv").read_bytes()


@pytest.fixture
def esquema_ejemplo(carpeta_ejemplo) -> dict:
    return json.loads((carpeta_ejemplo / "esquema_auditoria.json").read_text())


@pytest.fixture
def archivos_ejemplo() -> dict[str, str]:
    return ARCHIVOS
