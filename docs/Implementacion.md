# Notas de implementación del MVP

Complementa el [MOD v2.0](MOD_Tablero_AnyLogic_v2_MVP.md): qué quedó implementado, dónde, y qué
decisiones se tomaron al escribir el código que el MOD no fijaba.

## Cobertura del MOD

| MOD | Dónde |
|---|---|
| CU-01 importar corrida auditada | `apps/ingest/importadores.py::importar_paquete_auditoria` |
| CU-02 importar barrido | `apps/ingest/importadores.py::importar_kpis_barrido` |
| CU-03 dashboard de campaña | `apps/dashboard/agregados.py::dashboard` + `frontend/src/app/corridas/[runId]` |
| CU-04 vista "por qué" | `apps/dashboard/agregados.py::por_que` + `.../[runId]/porque` |
| CU-05 comparar dos corridas | `apps/dashboard/agregados.py::comparar` + `frontend/src/app/comparar` |
| §5 contrato de datos | `apps/ingest/esquema.py` |
| §6 modelo de datos | `apps/core/models.py` |
| §7 KPIs | `apps/dashboard/agregados.py` |
| §10 reglas de importación | `importadores.py` y `tests/test_importacion.py` |
| §11 pruebas | `backend/tests/` |

## Decisiones tomadas al implementar

### I-01 — Las columnas sin campo propio se guardan en `extra`

`decisiones_alternativas` tiene 97 columnas y el MVP mapea 22 a campos consultables. El resto se
guarda como JSON en `extra` en vez de descartarse: cuando haga falta una de esas columnas se
promueve a campo con una migración, sin tener que reimportar los paquetes ya cargados. Es lo
contrario de inventar columnas: no se agrega nada que el modelo no haya escrito.

### I-02 — El `run_id` es la identidad, el id numérico es un detalle

Los endpoints aceptan `E-00-R0` además del id de base de datos, porque es la clave con la que se
razona del lado de AnyLogic y con la que el usuario busca la corrida.

### I-03 — Reimportar una corrida la reemplaza

La reimportación de un `run_id` ya cargado borra sus filas y las vuelve a escribir dentro de la
misma transacción, y lo deja anotado como mensaje `INFO` del import. La alternativa (rechazar el
duplicado) obliga a borrar a mano cada vez que se corrige un paquete.

### I-04 — El nivel de servicio no se recalcula

Si la corrida tiene KPIs de `kpis_por_corrida.csv`, el dashboard muestra `nivel_servicio` y
`atraso_promedio_dias` tal como los calculó el modelo. Lo que sí se agrega desde
`AssignmentResult` es la cobertura de entrega (`toneladas_entregadas / toneladas_asignadas`), que
está declarada como tal y no se presenta como "nivel de servicio": dos formas distintas de medir
lo mismo que no coinciden es exactamente el bug silencioso que describe R-02.

### I-05 — Importación síncrona

Sin Celery (ADR-T02). El paquete de una corrida entra en una request; si en algún momento una
importación pasa de unos segundos, la condición de §14 para incorporar Celery estará cumplida y se
verá en el tiempo de respuesta, no antes.

## Calidad del import visible en el tablero

El detalle de la corrida muestra los mensajes del último import: `version_esquema` distinta de la
conocida, conteo de filas que no coincide con el manifiesto y filas con `descuadre_tn ≠ 0` (C-12).
Un paquete con cualquiera de esos tres queda `COMPLETADA_CON_ADVERTENCIAS`, no aceptado en
silencio.

## Pendiente antes de usarlo con datos reales

- Fase 0 del MOD: correr el importador contra un `esquema_auditoria.json` y un manifiesto de una
  corrida **real** de AnyLogic. El dataset de `datos_ejemplo/` reproduce el formato publicado pero
  no reemplaza esa verificación.
- Prueba de reconciliación de §11: comparar nivel de servicio y costo total (caja) del tablero web
  contra el tablero embebido de PLE para la misma corrida.
