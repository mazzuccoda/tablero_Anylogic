# MOD — Modelo Operativo y de Diseño
## Plataforma Web de Visualización de Resultados de AnyLogic

**Proyecto:** Tablero AnyLogic
**Repositorio:** `mazzuccoda/tablero_Anylogic`
**Versión del documento:** 2.0 — MVP
**Estado:** Documento base para la primera versión (Fases 0-3)
**Fecha:** 4 de agosto de 2026
**Responsable funcional:** Daniel Mazzucco
**Reemplaza:** MOD v1.0 (28 secciones, alcance completo), que queda como visión de largo plazo — ver §14.

---

## 0. Qué cambia respecto de la v1.0 y por qué

La v1.0 se escribió antes de que existiera un exportador real de datos del lado de AnyLogic. Desde entonces se mergeó **ADR-064** (auditoría de red): seis tablas CSV por corrida, con esquema publicado y validado (`V-AUD-01` a `V-AUD-11`), que dejan escrito qué alternativa se evaluó, cuál se eligió, por qué se descartaron las demás, qué pasó físicamente después y cuánto costó.

Esta versión del MOD:

1. Recorta el alcance de la v1.0 a lo mínimo que da valor real: **consumir lo que AnyLogic ya genera hoy y mostrar un dashboard que ayude a entender la red y dónde mejorarla.**
2. Reemplaza el contrato de datos inventado de la v1.0 (`daily_inventory.csv`, `lot_events.csv`, etc.) por las tablas **reales** de ADR-064 y `kpis_por_corrida.csv`.
3. Agrega la entidad que faltaba en la v1.0 y que es, en la práctica, la de mayor valor: `DecisionAlternative` (alternativas evaluadas y descartadas, con motivo).
4. Deja la estructura completa de la v1.0 (Nextcloud, Celery, multiusuario, animación, estadística de réplicas, reportes) como **visión futura**, no como trabajo de esta versión — ver §14, que resume qué se difiere y bajo qué condición conviene retomarlo.

---

## 1. Propósito

Construir la primera versión de una plataforma web que importe los resultados que AnyLogic ya produce hoy (`kpis_por_corrida.csv` del barrido, y las seis tablas de auditoría de red de una corrida puntual) y los muestre en un dashboard que responda dos preguntas:

- **¿Cómo está funcionando la red?** (KPIs de servicio, costos, utilización, cuellos de botella)
- **¿Qué la está limitando y qué conviene cambiar?** (alternativas más baratas descartadas, motivos de rechazo, esperas por capacidad)

La segunda pregunta es la que la v1.0 no podía responder porque no existía la tabla de decisiones. Es el foco de esta versión.

---

## 2. Alcance de esta versión (MVP)

### 2.1 Incluido

- Carga manual de un paquete de resultados de una corrida (las seis tablas de ADR-064 + `esquema_auditoria.json` + `manifiesto_auditoria_<run_id>.json`).
- Carga manual de `kpis_por_corrida.csv` (barrido de escenarios, KPIs agregados).
- Validación de estructura contra `esquema_auditoria.json` (no un esquema propio inventado).
- Almacenamiento en PostgreSQL.
- Un dashboard de campaña (equivalente al tablero embebido de PLE, pero persistente y navegable fuera de AnyLogic).
- La vista nueva: **"¿Por qué se atrasó o no se cumplió este pedido?"**, armada uniendo `decisiones_alternativas` → `asignaciones_elegidas` → `ejecucion_arcos` → `costos_eventos`.
- Comparación de dos corridas (agregados de `kpis_por_corrida.csv`; el drill-down de decisiones es por una corrida a la vez, porque el barrido corre con `nivelAuditoriaRed = DESACTIVADA` — ver §5.3).
- Un solo rol de usuario (vos). Sin autenticación multiusuario todavía — acceso restringido a nivel de red del mini lab.
- Despliegue Docker, administrable desde Portainer.

### 2.2 Explícitamente fuera de esta versión

- Sincronización con Nextcloud (carga manual alcanza para el volumen actual de corridas).
- Celery/Redis (no hay tareas asíncronas que lo justifiquen con carga manual y un usuario).
- Roles múltiples y autenticación granular.
- Animación temporal, mapas, Sankey, heatmaps.
- Estadística de réplicas (medias, percentiles, intervalos de confianza sobre el barrido).
- Reportes PDF, notificaciones, integración n8n.
- Recepción directa por API desde AnyLogic.

Todo esto queda documentado como visión futura en §14, no descartado.

---

## 3. Usuarios

Un solo rol en esta versión: **Analista** (vos). Puede importar corridas, consultar el dashboard, usar la vista "por qué", comparar dos corridas y exportar tablas filtradas.

La separación de roles de la v1.0 (Administrador / Analista / Visualizador / Auditor) queda documentada como diseño futuro (§14) para cuando haya más de un usuario real.

---

## 4. Casos de uso de esta versión

### CU-01 — Importar una corrida puntual (auditoría completa)

1. El usuario carga el paquete de una corrida con `nivelAuditoriaRed = COMPLETA` (las seis tablas + esquema + manifiesto).
2. El sistema valida columnas y claves contra `esquema_auditoria.json` (no contra un esquema propio).
3. El sistema valida `version_esquema`: si no coincide con la última conocida, avisa antes de importar, no importa a ciegas.
4. El sistema calcula los agregados de dashboard **a partir de `costos_eventos` filtrando `tipo_contable = CAJA`**, nunca sumando cualquier `amount_usd` sin distinguir caja de económico.
5. El sistema informa filas importadas por tabla y las compara contra `manifiesto_auditoria_<run_id>.json`; si no coinciden, la importación queda "completada con advertencias", no silenciosamente aceptada.

### CU-02 — Importar el resultado de un barrido

1. El usuario carga `kpis_por_corrida.csv`.
2. El sistema crea o actualiza una fila por corrida del barrido (una fila = un escenario + réplica).
3. No hay drill-down de decisiones para estas corridas — el dashboard lo indica explícitamente (ver §5.3), no lo oculta.

### CU-03 — Consultar el dashboard de una corrida

Igual que el tablero embebido de PLE (campaña, producción, transporte, pedidos, ventana marítima, capacidad finita, costos), pero navegable después de cerrado AnyLogic y comparable en el tiempo.

### CU-04 — Entender por qué un pedido no se cumplió

El usuario busca un `codigo_pedido`. El sistema muestra, en una sola vista:

- Las alternativas que se evaluaron para ese pedido (todas las rondas), con su costo, si eran factibles, y si no lo eran, por qué (`codigo_motivo`).
- Si hubo una alternativa **más barata que la elegida y no factible** (`es_mas_barata_no_factible`), destacada — es la pregunta "¿qué me está costando la restricción?".
- Los arcos físicos ejecutados (incluidas las dos esperas: portacontenedor y posición de consolidación), con duración real vs. esperada.
- Los cargos de costo asociados, separados por `tipo_contable`.

### CU-05 — Comparar dos corridas

Diferencia absoluta y porcentual de los KPIs de `kpis_por_corrida.csv` entre dos corridas (mismo escenario u otro).

---

## 5. Contrato de datos: lo que AnyLogic genera hoy

### 5.1 Principio

**No se inventa esquema propio.** El contrato de esta plataforma es el que ya publica AnyLogic: `resultados/esquema_auditoria.json` (columnas y clave de cada tabla) y `resultados/manifiesto_auditoria_<run_id>.json` (conteo de filas esperado, `version_esquema`). El validador de importación lee esos dos archivos antes de asumir ninguna columna.

Esto reemplaza la sección 10.2/10.3 de la v1.0, que definía un `manifest.json` y una lista de archivos propia sin correspondencia real del lado de AnyLogic.

### 5.2 Archivos por corrida puntual (`nivelAuditoriaRed = COMPLETA` o `RESUMIDA`)

| Archivo | Grano | Clave | Columnas |
|---|---|---|---|
| `decisiones_alternativas.csv` | una fila por alternativa evaluada, por ronda | `run_id`, `id_alternativa` | 97 |
| `asignaciones_elegidas.csv` | una fila por asignación ejecutada | `run_id`, `id_asignacion` | 30 |
| `ejecucion_arcos.csv` | una fila por movimiento o espera física terminada | `run_id`, `id_evento_arco` | 29 |
| `costos_eventos.csv` | una fila por cargo devengado | `run_id`, `id_costo` | 27 |
| `snapshot_inventario.csv` | una fila por día, ubicación y producto | `run_id`, `dia`, `ubicacion`, `producto` | 24 |
| `capacidad_por_dia.csv` | una fila por día, recurso y ubicación | `run_id`, `dia`, `tipo_recurso`, `ubicacion` | 13 |

Uniones estables (§7 de `Auditoria_de_Red.md`, adoptadas tal cual):

```
decisiones_alternativas.id_alternativa
  → asignaciones_elegidas.id_alternativa
    → ejecucion_arcos.id_asignacion
    → costos_eventos.id_asignacion
```

y por `id_contenedor` / `id_lote` para el costo que no nace de la asignación (por ejemplo, almacenaje contra el lote).

Reglas que el importador debe respetar porque así las define el modelo, no por elección propia de esta plataforma:

- Los importes **sólo** se suman desde `costos_eventos`, y sólo con `tipo_contable = CAJA`. Ninguna otra tabla trae dinero — ni `ejecucion_arcos` (a propósito no lleva importe, para no duplicar costos que puedan diferir).
- Un campo vacío es un dato que el modelo **no produce**, nunca un cero implícito. El importador no debe convertir vacíos en cero al calcular promedios ni sumas.
- `duracion_esperada_horas` negativa en `ejecucion_arcos` significa "no aplica" (esperar portacontenedor o posición no tiene techo físico) — no es un dato faltante ni un error de carga.

### 5.3 Archivo del barrido de escenarios

`kpis_por_corrida.csv`: una fila por corrida (escenario × réplica), KPIs agregados. Es lo único que existe para las corridas de un barrido, porque el barrido corre con `nivelAuditoriaRed = DESACTIVADA` (1.080 corridas en la misma JVM; auditar cada una sería mucho costo sin uso real). El dashboard debe dejar claro, cuando el usuario mira una corrida de barrido, que no hay vista "por qué" disponible para esa corrida — no debe fallar en silencio ni mostrar una vista vacía sin explicación.

---

## 6. Modelo de datos de esta versión

### 6.1 Entidades de control (igual que la v1.0)

`Project`, `Scenario`, `SimulationRun`, `ImportedFile` — sin cambios respecto de la v1.0, sección 11.1.

### 6.2 Entidades operativas (reemplazan la sección 11.2 de la v1.0)

#### `DecisionAlternative` — **nueva, no estaba en la v1.0**

Mapea `decisiones_alternativas.csv`. Campos mínimos para el MVP (subconjunto de las 97 columnas reales; se pueden agregar más sin romper nada):

- `simulation_run_id`, `id_decision`, `ronda`, `id_alternativa`
- `codigo_pedido`, `producto`, `circuito`
- `factible`, `orden_ranking`, `resultado_ejecucion`, `codigo_motivo`
- `costo_incremental_usd_tn`, `es_mas_barata_no_factible`
- `holgura_estimada_dias`, `llega_a_tiempo_estimado`

#### `AssignmentResult`

Mapea `asignaciones_elegidas.csv`. Reemplaza al `OrderResult` inventado de la v1.0: `id_asignacion`, `id_alternativa`, `codigo_pedido`, `toneladas_asignadas`, `toneladas_entregadas`, `dias_ciclo_real`, `costo_incremental_estimado`, `costo_real_contenedores_usd`, `desvio_costo_usd`, `cerrada`, `cancelada`.

#### `ArcExecution`

Mapea `ejecucion_arcos.csv`. Reemplaza a `TransportEvent`/`WarehouseMovement` de la v1.0, que en la v1.0 estaban separados sin necesidad: `tipo_arco`, `origen`, `destino`, `duracion_real_horas`, `duracion_esperada_horas`, `recurso_utilizado`, `estado_final`. **No lleva importe** — el costo se busca en `CostCharge`.

#### `CostCharge`

Mapea `costos_eventos.csv`. Reemplaza a `CostEvent` de la v1.0, agregando el campo que faltaba: **`tipo_contable` (`CAJA` / `ECONOMICO`)** — sin este campo, sumar `amount_usd` sin filtrar mezcla caja con costo de oportunidad.

#### `InventorySnapshot`

Mapea `snapshot_inventario.csv`. Se mantiene el nombre de la v1.0, columnas ajustadas al esquema real (incluye `descuadre_tn`, que en el dashboard debería mostrarse como indicador de salud del import: si no es 0 para alguna fila, algo se importó mal).

#### `ResourceCapacitySnapshot`

Mapea `capacidad_por_dia.csv`. Reemplaza a `ResourceUtilization` de la v1.0.

#### `ScenarioRunKpi`

Nueva, no estaba en la v1.0. Mapea una fila de `kpis_por_corrida.csv`. Es la única entidad disponible para las corridas de barrido (§5.3).

### 6.3 Qué se elimina de la v1.0

- `AlertEvent`: AnyLogic no genera alertas como tabla propia. Si hace falta, se derivan en consulta desde `DecisionAlternative` (`resultado_ejecucion = NO_FACTIBLE`) y `ResourceCapacitySnapshot` (ocupación cerca del máximo) — no se importa como archivo separado.
- `LotEvent` como tabla de eventos discretos: no existe del lado de AnyLogic. Lo que hay es `InventorySnapshot` con `lotes_abiertos` y `lote_mas_antiguo_dias` por día. Si más adelante hace falta trazabilidad de lote a nivel evento, es un pedido nuevo para el lado del modelo, no una entidad que este MVP pueda inventar sin datos reales detrás.

---

## 7. KPIs del dashboard (MVP)

Del listado amplio de la v1.0 (sección 12), esta versión implementa los que se pueden calcular directamente desde las tablas reales, sin inventar fórmulas propias que dupliquen lo que el modelo ya calculó:

- **Servicio:** nivel de servicio, atraso promedio, toneladas exportadas — leídos de `kpis_por_corrida.csv` o agregados de `AssignmentResult`, no recalculados con una fórmula propia de "on time" que pueda diferir de la del modelo.
- **Costo:** costo total (caja), costo por tonelada, desglose por categoría — sumando `CostCharge` filtrado por `tipo_contable = CAJA`.
- **Restricción:** cantidad de `es_mas_barata_no_factible`, desglose de `codigo_motivo`, espera promedio por tipo de arco (`ESPERA_PORTACONTENEDOR`, `ESPERA_POSICION`) — estos son los KPIs nuevos que la v1.0 no podía tener porque no existía la tabla de decisiones.
- **Capacidad:** ocupación por recurso y ubicación desde `ResourceCapacitySnapshot`.

Los KPIs que la v1.0 proponía y que hoy no tienen tabla de origen (por ejemplo, "costo por pérdida de ventana" desagregado, o estadística de réplicas) quedan fuera de esta versión — no se estiman con supuestos propios.

---

## 8. Arquitectura de esta versión

```text
AnyLogic (corrida puntual COMPLETA, o barrido)
   |
   | esquema_auditoria.json + manifiesto + 6 CSV,  o  kpis_por_corrida.csv
   v
Carga manual (navegador)
   |
   v
Servicio de ingestión (Django, síncrono)
   |
   +--> validación contra esquema_auditoria.json
   +--> importación transaccional
   +--> KPIs leídos/agregados, no recalculados con lógica propia
   |
   v
PostgreSQL
   |
   v
Django REST API
   |
   v
Next.js / React
   |
   v
Usuario (vos)
```

Diferencias deliberadas contra la v1.0: sin Celery/Redis (la importación es síncrona porque el volumen de una carga manual de una corrida es manejable en segundos, no minutos), sin Nextcloud, sin proxy Nginx separado si Django lo sirve directamente en el mini lab.

### 8.1 Tecnologías (recorte de la v1.0, sección 7.3)

| Componente | Tecnología | Igual que v1.0 |
|---|---|---|
| Backend | Django + DRF | Sí |
| Frontend | Next.js + TypeScript | Sí |
| Base de datos | PostgreSQL | Sí |
| Gráficos | Apache ECharts | Sí |
| Tablas | TanStack Table | Sí |
| Estilos | Tailwind + shadcn/ui | Sí |
| Contenedores | Docker + Portainer | Sí |
| Tareas en segundo plano | — | **No en esta versión** (Celery/Redis quedan en §14) |
| Archivos externos | — | **No en esta versión** (Nextcloud queda en §14) |

### 8.2 Servicios Docker de esta versión

```yaml
services:
  db:        # PostgreSQL
  backend:   # Django + DRF, sirve estático en dev
  frontend:  # Next.js
  # nginx, redis, celery, celery-beat, nextcloud-sync: NO en esta versión
```

---

## 9. Endpoints de esta versión

```http
GET    /api/v1/scenarios/
GET    /api/v1/simulation-runs/
POST   /api/v1/imports/upload/
GET    /api/v1/imports/{id}/

GET    /api/v1/simulation-runs/{id}/dashboard/
GET    /api/v1/simulation-runs/{id}/inventory/
GET    /api/v1/simulation-runs/{id}/costs/
GET    /api/v1/simulation-runs/{id}/capacity/

GET    /api/v1/orders/{codigo_pedido}/why/      # CU-04, la vista nueva
POST   /api/v1/comparisons/                      # CU-05, sobre ScenarioRunKpi
```

`/orders/{codigo_pedido}/why/` es el endpoint que no estaba en la v1.0: devuelve la unión ya resuelta de `DecisionAlternative` + `AssignmentResult` + `ArcExecution` + `CostCharge` para ese pedido, para que el frontend no tenga que hacer cuatro llamadas y cruzarlas.

---

## 10. Reglas de importación (recorte de la v1.0, sección 15)

Se mantienen de la v1.0: importación transaccional, prevención de duplicados por `run_id` + checksum, clasificación de errores en crítico/advertencia, idempotencia.

Se agrega, específico de esta versión:

- Si `version_esquema` del paquete importado no coincide con la última conocida por la plataforma, la importación se marca "completada con advertencias" y el dashboard lo muestra — no se asume que las columnas significan lo mismo que antes.
- Si el conteo de filas importado no coincide con `manifiesto_auditoria_<run_id>.json`, misma clasificación.
- Si `descuadre_tn` de `InventorySnapshot` no es 0 en alguna fila importada, se registra como advertencia de calidad de datos, visible en el detalle de la corrida.

---

## 11. Pruebas de esta versión

Recorte de la v1.0 (sección 21), sin frontend E2E todavía (un solo usuario, iteración rápida):

- Backend: importadores, validadores contra `esquema_auditoria.json`, cálculo de agregados desde `CostCharge`/`AssignmentResult`, endpoint `/why/`.
- Datos: archivo válido, columna faltante, `version_esquema` distinta, `run_id` duplicado, conteo de filas que no coincide con el manifiesto, `descuadre_tn` distinto de cero.
- Deployment: creación desde cero, actualización, recuperación de volumen de PostgreSQL.

**Prueba de aceptación específica de esta versión:** para una corrida importada, el nivel de servicio y el costo total (caja) que muestra el dashboard web deben coincidir con lo que muestra el tablero embebido de PLE para esa misma corrida. Es la reconciliación cruzada que la v1.0 no tenía como criterio explícito.

---

## 12. Criterios de aceptación del MVP

El MVP se acepta cuando:

1. El stack (db + backend + frontend) se despliega desde Portainer.
2. Se puede cargar manualmente un paquete de auditoría completa y uno de barrido.
3. Un paquete inválido (columna faltante, `version_esquema` desconocida) se rechaza o se marca con advertencia, con detalle.
4. El dashboard de campaña muestra los mismos KPIs de servicio, costo y capacidad que el tablero embebido de PLE, para la misma corrida (prueba de reconciliación de §11).
5. La vista `/orders/{codigo_pedido}/why/` muestra, para un pedido atrasado real, sus alternativas evaluadas, el motivo de descarte y si hubo una alternativa más barata no factible.
6. Se pueden comparar dos corridas del barrido por sus KPIs agregados.
7. Una tabla filtrada se puede exportar a CSV.
8. La base de datos sobrevive a la recreación de contenedores.
9. No hay secretos en el repositorio.
10. Existe un conjunto de datos de ejemplo (la corrida de referencia de `V-AUD-01..11`, `E-00-R0`).

---

## 13. Roadmap de esta versión

### Fase 0 — Contrato de datos real

- Adoptar `esquema_auditoria.json` y `manifiesto_auditoria_<run_id>.json` tal cual los publica AnyLogic.
- Confirmar con Devin (lado AnyLogic) el formato exacto de ambos archivos sobre una corrida real, antes de escribir el validador.

### Fase 1 — Base del repositorio

- Estructura, Dockerfiles, Compose mínimo (db + backend + frontend), healthchecks.

### Fase 2 — Importación manual

- `Project`, `Scenario`, `SimulationRun`, `ImportedFile`.
- Importador de las seis tablas de auditoría + `kpis_por_corrida.csv`.
- Validación contra esquema real, reglas de §10.

### Fase 3 — Dashboard y vista "por qué"

- Dashboard de campaña equivalente al de PLE.
- Vista `/orders/{codigo_pedido}/why/` (CU-04).
- Comparador de dos corridas (CU-05, sobre `ScenarioRunKpi`).

Sin fase 4 en adelante en esta versión — ver §14.

---

## 14. Visión futura (de la v1.0, diferida, no descartada)

Se mantiene como referencia para cuando corresponda retomarlo, con la condición que lo activa:

| Bloque de la v1.0 | Se retoma cuando |
|---|---|
| Nextcloud + sincronización automática | El volumen de corridas para cargar manualmente se vuelva una fricción real, no antes |
| Celery + Redis | Haya una tarea de importación que tarde más de unos segundos (por ejemplo, importar el barrido completo con auditoría activada, hoy fuera de alcance del propio modelo) |
| Roles múltiples y autenticación | Haya más de un usuario real usando la plataforma |
| Animación temporal, mapas, Sankey, heatmaps | El dashboard de KPIs y la vista "por qué" ya estén en uso y se identifique una pregunta concreta que solo un gráfico animado responda mejor |
| Estadística de réplicas (percentiles, intervalos de confianza) | El barrido se corra con más frecuencia como parte del flujo de decisión, no solo como validación puntual |
| Reportes PDF, n8n, notificaciones | Haya un consumidor de esos reportes que no sea el propio analista mirando el dashboard |
| API directa desde AnyLogic | La carga manual, hoy con pocas corridas, se vuelva un cuello de botella real |

La condición común a todas: **evidencia de necesidad real de uso, no anticipación.** Es la misma lógica que Devin aplicó en ADR-064 (auditar solo cuando se usa el resultado, streaming en vez de acumular "por si se corta la corrida") — construir cuando hay una pregunta concreta sin responder, no antes.

---

## 15. Riesgos de esta versión

### R-01 — El esquema de AnyLogic sigue cambiando

Ya ocurrió: `version_esquema = ADR-064.1` está pensado para cambiar. Mitigación: el validador de importación lee el esquema publicado en cada paquete, no lo asume fijo en el código del backend.

### R-02 — Confundir `tipo_contable`

Sumar `costos_eventos` sin filtrar por `CAJA`/`ECONOMICO` da un total que no coincide con el tablero de PLE. Mitigación: la prueba de aceptación de §11 lo detecta antes de que sea un bug silencioso en producción.

### R-03 — El drill-down no existe para corridas de barrido

Un usuario puede esperar la vista "por qué" para cualquier corrida y no está disponible si `nivelAuditoriaRed = DESACTIVADA`. Mitigación: el dashboard lo indica explícitamente en vez de mostrar una vista vacía.

---

## 16. Definición de terminado (igual que v1.0, sección 25)

Una funcionalidad de esta versión se considera terminada cuando tiene requerimiento definido, diseño técnico, código revisado, pruebas, manejo de errores, documentación, funciona en Docker y desde Portainer, no expone secretos y cumple sus criterios de aceptación.

---

## 17. Decisiones de arquitectura de esta versión

### ADR-T01

**Decisión:** el contrato de datos es el que publica AnyLogic (`esquema_auditoria.json` + `manifiesto_auditoria_<run_id>.json`), no un esquema propio.
**Motivo:** un esquema inventado sin contraparte real es lo que hizo inviable la v1.0 durante la primera semana de este proyecto; mantener dos esquemas es mantener dos fuentes de verdad que pueden divergir.

### ADR-T02

**Decisión:** sin Celery/Redis/Nextcloud en el MVP.
**Motivo:** ninguno de los tres resuelve un problema que exista hoy con carga manual y un usuario. Se agregan cuando la evidencia de uso lo pida (§14).

### ADR-T03

**Decisión:** `DecisionAlternative` es una entidad de primera clase del modelo de datos, no un derivado opcional.
**Motivo:** es la tabla que responde la pregunta que motiva todo el proyecto — qué restringe la red y cuánto cuesta esa restricción — y no tenía lugar en el modelo de datos de la v1.0.

### ADR-T04

**Decisión:** los importes del dashboard sólo se calculan sumando `costos_eventos` con `tipo_contable = CAJA`.
**Motivo:** es la misma regla que usa el tablero embebido de PLE; usar cualquier otra fuente o mezclar tipos contables produce un total que no reconcilia.

---

## 18. Próximo entregable recomendado

Un prompt para Devin (lado AnyLogic) que confirme, sobre una corrida real, el contenido exacto de `esquema_auditoria.json` y `manifiesto_auditoria_<run_id>.json` — son la base del validador de Fase 0 — y que entregue una corrida de ejemplo (`E-00-R0`, la misma de `V-AUD-01..11`) como dataset de referencia para las pruebas de importación de este proyecto.
