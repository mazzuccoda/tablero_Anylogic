"""Modelo de datos del tablero (MOD v2.0, seccion 6).

Las entidades operativas mapean una a una las tablas que publica AnyLogic (ADR-064).
Las columnas del CSV que no tienen campo propio se guardan en `extra`, para no perder
informacion sin inventar un esquema paralelo: el contrato es el de AnyLogic (ADR-T01).
"""

from django.db import models


class TipoCorrida(models.TextChoices):
    AUDITORIA = "AUDITORIA", "Corrida puntual auditada"
    BARRIDO = "BARRIDO", "Corrida de barrido (sin auditoria)"


class NivelAuditoria(models.TextChoices):
    DESACTIVADA = "DESACTIVADA", "Desactivada"
    RESUMIDA = "RESUMIDA", "Resumida"
    COMPLETA = "COMPLETA", "Completa"


class EstadoImportacion(models.TextChoices):
    EN_CURSO = "EN_CURSO", "En curso"
    COMPLETADA = "COMPLETADA", "Completada"
    COMPLETADA_CON_ADVERTENCIAS = "COMPLETADA_CON_ADVERTENCIAS", "Completada con advertencias"
    RECHAZADA = "RECHAZADA", "Rechazada"


class TipoContable(models.TextChoices):
    CAJA = "CAJA", "Caja"
    ECONOMICO = "ECONOMICO", "Economico"


class Project(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Scenario(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scenarios")
    codigo = models.CharField(max_length=60)
    descripcion = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(fields=["project", "codigo"], name="scenario_unico_por_project")
        ]

    def __str__(self) -> str:
        return self.codigo


class SimulationRun(models.Model):
    """Una corrida. `run_id = <id_escenario>-R<replica>` es la clave de AnyLogic."""

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="runs")
    run_id = models.CharField(max_length=80, unique=True)
    replica = models.IntegerField(null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=TipoCorrida.choices)
    nivel_auditoria = models.CharField(
        max_length=20, choices=NivelAuditoria.choices, default=NivelAuditoria.DESACTIVADA
    )
    version_esquema = models.CharField(max_length=30, blank=True)
    version_modelo = models.CharField(max_length=60, blank=True)
    duracion_campania_dias = models.IntegerField(null=True, blank=True)
    # Ancla de calendario de la campania (ADR-064.2, MOD v4.1): un paquete importado con un
    # esquema anterior no la trae, y agrupar por semana/mes/anio sin ella no significa nada.
    fecha_inicio_campania = models.DateField(null=True, blank=True)
    generado = models.CharField(max_length=80, blank=True)
    importado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-importado"]

    def __str__(self) -> str:
        return self.run_id

    @property
    def tiene_drill_down(self) -> bool:
        """La vista "por que" solo existe si la corrida se audito (MOD v2.0, seccion 5.3)."""
        return self.tipo == TipoCorrida.AUDITORIA


class ImportBatch(models.Model):
    """Una importacion. Guarda el resultado de la validacion contra el esquema publicado."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="imports", null=True, blank=True
    )
    estado = models.CharField(
        max_length=30, choices=EstadoImportacion.choices, default=EstadoImportacion.EN_CURSO
    )
    version_esquema = models.CharField(max_length=30, blank=True)
    mensajes = models.JSONField(default=list)
    filas_por_tabla = models.JSONField(default=dict)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self) -> str:
        return f"Import {self.pk} ({self.estado})"

    @property
    def advertencias(self) -> list:
        return [m for m in self.mensajes if m.get("nivel") == "ADVERTENCIA"]

    @property
    def errores(self) -> list:
        return [m for m in self.mensajes if m.get("nivel") == "ERROR"]


class ImportedFile(models.Model):
    """Un archivo del paquete. El checksum evita reimportar el mismo archivo dos veces."""

    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="archivos"
    )
    nombre = models.CharField(max_length=200)
    tabla = models.CharField(max_length=60, blank=True)
    checksum_sha256 = models.CharField(max_length=64)
    filas_importadas = models.IntegerField(default=0)
    filas_manifiesto = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class FilaAuditoria(models.Model):
    """Base de las tablas de auditoria.

    Las columnas del CSV sin campo propio viven en `extra`: el paquete trae 97 columnas en
    `decisiones_alternativas` y descartarlas obligaria a reimportar cuando hagan falta.

    Las claves que declara el esquema (por ejemplo `id_alternativa`) no son unicas en los paquetes
    reales: el modelo reutiliza un `id_decision` en dias distintos. Por eso son indices y no
    restricciones: la base guarda el paquete tal como lo escribio AnyLogic y el importador avisa
    de las claves repetidas, en vez de rechazar la corrida entera. La idempotencia no depende de
    la unicidad de fila: reimportar una corrida borra y reescribe todas sus filas.
    """

    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class DecisionAlternative(FilaAuditoria):
    """`decisiones_alternativas.csv`. Entidad de primera clase del MVP (ADR-T03)."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="decisiones"
    )
    id_decision = models.CharField(max_length=80)
    ronda = models.IntegerField(null=True, blank=True)
    id_alternativa = models.CharField(max_length=80)
    codigo_pedido = models.CharField(max_length=80, blank=True)
    producto = models.CharField(max_length=80, blank=True)
    circuito = models.CharField(max_length=80, blank=True)
    origen_stock = models.CharField(max_length=80, blank=True)
    destino_final = models.CharField(max_length=80, blank=True)
    factible = models.BooleanField(null=True)
    orden_ranking = models.IntegerField(null=True, blank=True)
    resultado_ejecucion = models.CharField(max_length=30, blank=True)
    codigo_motivo = models.CharField(max_length=60, blank=True)
    detalle_motivo = models.TextField(blank=True)
    costo_incremental_usd_tn = models.FloatField(null=True, blank=True)
    costo_end_to_end_usd_tn = models.FloatField(null=True, blank=True)
    es_mas_barata_no_factible = models.BooleanField(null=True)
    holgura_estimada_dias = models.FloatField(null=True, blank=True)
    llega_a_tiempo_estimado = models.BooleanField(null=True)
    toneladas_solicitadas = models.FloatField(null=True, blank=True)
    toneladas_factibles = models.FloatField(null=True, blank=True)
    toneladas_tomadas = models.FloatField(null=True, blank=True)
    dia_simulacion = models.FloatField(null=True, blank=True)
    # ADR-064.2: fecha = fecha_inicio_campania + (dia_campania - 1). No se recalcula aca, se
    # guarda tal como la publica el modelo (ADR-T01).
    fecha = models.DateField(null=True, blank=True)
    fecha_cutoff = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "id_alternativa"]),
            models.Index(fields=["simulation_run", "codigo_pedido"]),
            models.Index(fields=["simulation_run", "codigo_motivo"]),
        ]

    def __str__(self) -> str:
        return self.id_alternativa


class AssignmentResult(FilaAuditoria):
    """`asignaciones_elegidas.csv`."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="asignaciones"
    )
    id_asignacion = models.CharField(max_length=80)
    id_decision = models.CharField(max_length=80, blank=True)
    id_alternativa = models.CharField(max_length=80, blank=True)
    codigo_pedido = models.CharField(max_length=80, blank=True)
    producto = models.CharField(max_length=80, blank=True)
    # ADR-T05 (MOD v6): idem CostCharge.material.
    material = models.CharField(max_length=80, blank=True)
    origen = models.CharField(max_length=80, blank=True)
    circuito = models.CharField(max_length=80, blank=True)
    dia_asignacion = models.FloatField(null=True, blank=True)
    dia_ultima_entrega = models.FloatField(null=True, blank=True)
    toneladas_asignadas = models.FloatField(null=True, blank=True)
    toneladas_entregadas = models.FloatField(null=True, blank=True)
    contenedores_creados = models.IntegerField(null=True, blank=True)
    contenedores_entregados = models.IntegerField(null=True, blank=True)
    costo_incremental_estimado = models.FloatField(null=True, blank=True)
    costo_real_contenedores_usd = models.FloatField(null=True, blank=True)
    desvio_costo_usd = models.FloatField(null=True, blank=True)
    dias_ciclo_real = models.FloatField(null=True, blank=True)
    cerrada = models.BooleanField(null=True)
    cancelada = models.BooleanField(null=True)
    motivo_asignacion = models.CharField(max_length=120, blank=True)
    fecha_asignacion = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "id_asignacion"]),
            models.Index(fields=["simulation_run", "codigo_pedido"]),
        ]

    def __str__(self) -> str:
        return self.id_asignacion


class ArcExecution(FilaAuditoria):
    """`ejecucion_arcos.csv`. No lleva importe a proposito (ADR-064, seccion 5.3)."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="arcos"
    )
    id_evento_arco = models.CharField(max_length=80)
    id_decision = models.CharField(max_length=80, blank=True)
    id_alternativa = models.CharField(max_length=80, blank=True)
    id_asignacion = models.CharField(max_length=80, blank=True)
    id_envio = models.CharField(max_length=80, blank=True)
    id_contenedor = models.CharField(max_length=80, blank=True)
    id_lote = models.CharField(max_length=80, blank=True)
    codigo_pedido = models.CharField(max_length=80, blank=True)
    producto = models.CharField(max_length=80, blank=True)
    tipo_arco = models.CharField(max_length=60, blank=True)
    origen = models.CharField(max_length=80, blank=True)
    destino = models.CharField(max_length=80, blank=True)
    toneladas = models.FloatField(null=True, blank=True)
    contenedores = models.IntegerField(null=True, blank=True)
    dia_inicio = models.FloatField(null=True, blank=True)
    dia_fin = models.FloatField(null=True, blank=True)
    duracion_real_horas = models.FloatField(null=True, blank=True)
    duracion_esperada_horas = models.FloatField(null=True, blank=True)
    recurso_utilizado = models.CharField(max_length=80, blank=True)
    estado_final = models.CharField(max_length=60, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "id_evento_arco"]),
            models.Index(fields=["simulation_run", "codigo_pedido"]),
            models.Index(fields=["simulation_run", "id_asignacion"]),
            models.Index(fields=["simulation_run", "tipo_arco"]),
        ]

    @property
    def duracion_esperada_aplica(self) -> bool:
        """Negativa significa "no aplica" (esperas sin techo fisico), no dato faltante."""
        return self.duracion_esperada_horas is not None and self.duracion_esperada_horas >= 0

    def __str__(self) -> str:
        return f"{self.tipo_arco} {self.id_evento_arco}"


class CostCharge(FilaAuditoria):
    """`costos_eventos.csv`. Unica fuente de importes del tablero (ADR-T04)."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="costos"
    )
    id_costo = models.CharField(max_length=80)
    dia = models.FloatField(null=True, blank=True)
    dia_campania = models.IntegerField(null=True, blank=True)
    fecha = models.DateField(null=True, blank=True)
    tipo_contable = models.CharField(max_length=20, choices=TipoContable.choices, blank=True)
    categoria = models.CharField(max_length=60, blank=True)
    codigo_pedido = models.CharField(max_length=80, blank=True)
    id_asignacion = models.CharField(max_length=80, blank=True)
    id_decision = models.CharField(max_length=80, blank=True)
    id_contenedor = models.CharField(max_length=80, blank=True)
    id_lote = models.CharField(max_length=80, blank=True)
    producto = models.CharField(max_length=80, blank=True)
    # ADR-T05 (MOD v6): declarados en esquema_auditoria.json desde siempre, pero sin campo propio
    # caian en `extra`. Los pedidos de la matriz "estrategia por producto" y el explorador
    # necesitan filtrar por ellos, asi que se promueven a columna.
    material = models.CharField(max_length=80, blank=True)
    proveedor = models.CharField(max_length=80, blank=True)
    circuito = models.CharField(max_length=80, blank=True)
    origen = models.CharField(max_length=80, blank=True)
    destino = models.CharField(max_length=80, blank=True)
    sitio = models.CharField(max_length=80, blank=True)
    unidad = models.CharField(max_length=40, blank=True)
    cantidad = models.FloatField(null=True, blank=True)
    tarifa = models.FloatField(null=True, blank=True)
    importe_usd = models.FloatField(null=True, blank=True)
    alcance = models.CharField(max_length=30, blank=True)
    es_incremental = models.BooleanField(null=True)
    motivo = models.CharField(max_length=160, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "id_costo"]),
            models.Index(fields=["simulation_run", "tipo_contable"]),
            models.Index(fields=["simulation_run", "codigo_pedido"]),
            models.Index(fields=["simulation_run", "categoria"]),
            models.Index(fields=["simulation_run", "fecha"]),
        ]

    def __str__(self) -> str:
        return self.id_costo


class InventorySnapshot(FilaAuditoria):
    """`snapshot_inventario.csv`."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="inventario"
    )
    dia = models.IntegerField()
    fecha = models.DateField(null=True, blank=True)
    ubicacion = models.CharField(max_length=80)
    tipo_ubicacion = models.CharField(max_length=60, blank=True)
    producto = models.CharField(max_length=80)
    capacidad_tn = models.FloatField(null=True, blank=True)
    stock_inicial_dia_tn = models.FloatField(null=True, blank=True)
    stock_fisico_tn = models.FloatField(null=True, blank=True)
    stock_libre_tn = models.FloatField(null=True, blank=True)
    ingresos_dia_tn = models.FloatField(null=True, blank=True)
    egresos_dia_tn = models.FloatField(null=True, blank=True)
    produccion_dia_tn = models.FloatField(null=True, blank=True)
    ocupacion_pct = models.FloatField(null=True, blank=True)
    lotes_abiertos = models.IntegerField(null=True, blank=True)
    lote_mas_antiguo_dias = models.FloatField(null=True, blank=True)
    descuadre_tn = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "dia"]),
            models.Index(fields=["simulation_run", "ubicacion", "producto"]),
            models.Index(fields=["simulation_run", "fecha"]),
        ]

    def __str__(self) -> str:
        return f"{self.ubicacion}/{self.producto} dia {self.dia}"


class ResourceCapacitySnapshot(FilaAuditoria):
    """`capacidad_por_dia.csv`."""

    simulation_run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="capacidad"
    )
    dia = models.IntegerField()
    fecha = models.DateField(null=True, blank=True)
    tipo_recurso = models.CharField(max_length=60)
    ubicacion = models.CharField(max_length=80)
    capacidad_nominal = models.FloatField(null=True, blank=True)
    reservada = models.FloatField(null=True, blank=True)
    consumida = models.FloatField(null=True, blank=True)
    liberada = models.FloatField(null=True, blank=True)
    ocupada = models.FloatField(null=True, blank=True)
    libre = models.FloatField(null=True, blank=True)
    cola = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["simulation_run", "tipo_recurso"]),
            models.Index(fields=["simulation_run", "dia"]),
            models.Index(fields=["simulation_run", "fecha"]),
        ]

    def __str__(self) -> str:
        return f"{self.tipo_recurso}@{self.ubicacion} dia {self.dia}"


class ScenarioRunKpi(models.Model):
    """Una fila de `kpis_por_corrida.csv`: lo unico que existe para el barrido (seccion 5.3)."""

    simulation_run = models.OneToOneField(
        SimulationRun, on_delete=models.CASCADE, related_name="kpis"
    )
    semilla = models.BigIntegerField(null=True, blank=True)
    valores = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"KPIs de {self.simulation_run.run_id}"
