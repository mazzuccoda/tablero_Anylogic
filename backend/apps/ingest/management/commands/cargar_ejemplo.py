"""Importa el paquete de ejemplo `E-00-R0` y el barrido de `datos_ejemplo/`."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ingest.importadores import (
    ImportacionRechazada,
    importar_kpis_barrido,
    importar_paquete_auditoria,
)

RAIZ = Path(__file__).resolve().parents[5] / "datos_ejemplo"


class Command(BaseCommand):
    help = "Carga el dataset de ejemplo (corrida E-00-R0 y kpis_por_corrida.csv)."

    def add_arguments(self, parser):
        parser.add_argument("--datos", default=str(RAIZ), help="carpeta datos_ejemplo")

    def handle(self, *args, **opciones):
        raiz = Path(opciones["datos"])
        carpeta = raiz / "E-00-R0"
        if not carpeta.is_dir():
            raise CommandError(f"no existe {carpeta}: correr datos_ejemplo/generar_ejemplo.py")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for archivo in sorted(carpeta.iterdir()):
                zf.write(archivo, archivo.name)

        try:
            lote = importar_paquete_auditoria(buffer.getvalue(), "paquete_auditoria_E-00-R0.zip")
        except ImportacionRechazada as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"corrida importada: {lote.simulation_run.run_id} ({lote.estado})")
        for mensaje in lote.mensajes:
            self.stdout.write(f"  [{mensaje['nivel']}] {mensaje['texto']}")

        kpis = raiz / "kpis_por_corrida.csv"
        if kpis.is_file():
            lote_barrido = importar_kpis_barrido(kpis.read_bytes(), kpis.name)
            filas = lote_barrido.filas_por_tabla.get("kpis_por_corrida", 0)
            self.stdout.write(f"barrido importado: {filas} corridas")
