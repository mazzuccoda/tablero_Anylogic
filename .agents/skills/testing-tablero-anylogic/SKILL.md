---
name: testing-tablero-anylogic
description: Cómo levantar y probar end-to-end el tablero AnyLogic (backend Django/DRF + frontend Next.js), qué datos de ejemplo usar y qué trampas hay al sembrar la base.
---

# Probar el tablero AnyLogic end-to-end

## Levantar el stack sin Docker

```bash
cd backend && .venv/bin/python manage.py migrate \
  && .venv/bin/python manage.py cargar_ejemplo \
  && .venv/bin/python manage.py runserver 0.0.0.0:8000

cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev
```

- Sin `POSTGRES_HOST` el backend usa SQLite (`backend/db.sqlite3`); borrarlo es la forma más
  rápida de volver a un estado limpio antes de re-`migrate`.
- No hay login ni credenciales: el frontend hace todo el fetch client-side contra
  `NEXT_PUBLIC_API_URL`. Si la UI aparece vacía, verificar primero que el backend responde en
  `http://localhost:8000/api/v1/simulation-runs/?limit=200`.
- El frontend dev server tarda ~20 s en compilar la primera ruta; esperar antes de concluir que
  algo falla.

## Trampa conocida: el barrido puede pisar la corrida auditada

`datos_ejemplo/kpis_por_corrida.csv` incluye la fila `E-00, replica 0`, que genera el mismo
`run_id` (`E-00-R0`) que el paquete de auditoría. El importador del barrido hacía
`update_or_create` con `tipo=BARRIDO` / `nivel_auditoria=DESACTIVADA`, así que **importar el
barrido después del zip degradaba la corrida auditada y hacía desaparecer el drill-down**.
`manage.py cargar_ejemplo` importa el zip y después el CSV, con lo cual el estado sembrado por
defecto podía quedar sin corridas auditadas.

Desde el PR del Cost Explorer esto está arreglado: el import del CSV emite
`INFO — E-00-R0 ya estaba importada como corrida auditada: se le agregaron los KPIs del barrido y
se conservo el drill-down`. Ese INFO es la señal a buscar; si no aparece, sospechar una regresión.

Puede volver a romperse; en cualquier sesión de testing conviene:

1. Después de sembrar, comprobar en `/` que existe el panel "Corridas auditadas" con `E-00-R0`.
2. Si no existe, reimportar el paquete de auditoría desde `/importar`
   (o por `POST /api/v1/imports/upload/`) para restaurar la corrida antes de seguir.
3. Verificar el orden inverso también (zip después de CSV) como caso de prueba explícito.

## Paquete real de AnyLogic

`datos_ejemplo/E-00-R0/Ejemplo_real.zip` (2,7 MB) es el paquete real. Importarlo tarda ~15 s con
SQLite y deja: 1413 asignaciones / 4004 capacidad / 106365 costos / 25974 decisiones /
10910 arcos / 2702 inventario. Termina en `COMPLETADA_CON_ADVERTENCIAS` con dos avisos esperados:
la ADVERTENCIA de `id_alternativa` repetida (36 casos, ej. `P00633-D1-A1`) y el INFO de
`asignaciones_capacidad.csv` (archivo que el esquema no declara). Valores de referencia:

- CAJA `USD 5.760.244,18` en 105 270 eventos; ECONOMICO `USD 435.478,72` en 1 095, **nunca sumados**.
- `tn_entregadas = 30.314,5177` → `USD/tn = 190,02`.
- Pedidos útiles para `/porque`: `P00978` (36 alternativas, costo de caja USD 5.550) y `P00633`
  (288 alternativas, 286 no factibles, sin costos → "sin dato" / USD 0).

Para calcular la verdad de campo sin pasar por la app, leer `costos_eventos.csv` y
`asignaciones_elegidas.csv` directamente del ZIP con `zipfile` + `csv.DictReader`. Es la única
forma de distinguir "el agregado está bien" de "el agregado y el import están mal igual".

## Cost Explorer

```
GET /api/v1/simulation-runs/{run_id}/cost-explorer/
    summary | by-stage | by-category | reconciliation | waterfall | by-arc | constraints
    by-dimension/{producto|circuito|sitio|origen|destino|alcance|unidad|motivo}
    by-object/{lote|contenedor|pedido}
    events/?limit&offset&orden       (limit máximo 500; orden: importe, categoria, dia, dia_desc)
```

UI: `/corridas/{run_id}/costos`, alcanzable con el botón **"Explorar costos"** del dashboard, que
sólo se renderiza si `tiene_drill_down` (es decir, nunca en corridas de barrido).

- `tipo_contable` arranca en `CAJA`; el otro tipo viaja en `contraparte`, nunca sumado.
- Filtros por lista blanca: `tipo_contable, categoria, producto, circuito, origen, destino, sitio,
  alcance, unidad, codigo_pedido, id_asignacion, id_contenedor, id_lote, motivo, etapa,
  dia_desde, dia_hasta`. Cualquier otro nombre → 400. Los **valores** de los campos de texto no se
  validan contra la corrida: un `producto` inexistente devuelve 200 con 0 filas, y la UI lo muestra
  con un aviso ámbar de "recorte sin filas" y todas las tarjetas en "sin dato" (nunca USD 0).
- Una corrida de barrido devuelve 409 con el motivo en **todos** los endpoints; la página de costos
  lo pinta como mensaje en rojo. Comprobarlo, no asumirlo.
- Con el paquete real todos responden en < 0,4 s; si alguno tarda segundos, sospechar que el
  agregado se está haciendo en Python en vez de en la base. La pantalla dispara ~11 requests en
  paralelo, así que la primera pintura tarda 8-10 s con el dev server.
- Valores de referencia con el paquete real (verificables contra los CSV crudos):
  nodo (origen = destino) `1.377.631,84` + arco `4.382.612,34` = total;
  JUGO `3.464.625,97` / CASCARA `1.943.668,21` / ACEITE `351.950,00`;
  cargos sin `codigo_pedido` `2.646.631,84` (por eso la dimensión `codigo_pedido` es PARCIAL);
  sobrecosto por restricción `164.120,94` en 139 decisiones, todo `SIN_CAPACIDAD_ANTES_CUTOFF`
  (es un contrafactual: **no** debe entrar en el total de caja ni en la reconciliación);
  objeto `pedido` P01319 = USD 6.820,7 / 24,28 tn = 280,92 USD/tn.

### Posibles bugs a revisar en la pantalla de costos

- **Selector de objeto (Lote / Contenedor / Pedido)**: puede quedarse pegado. Se vio que al cambiar
  de objeto la tabla mantenía los importes del objeto anterior y mostraba "sin dato" en la columna
  de identificador, con un `Warning: Encountered two children with the same key` en la consola
  (las filas se keyean con `String(fila[objeto.clave] ?? "")`, y al cambiar la clave todas las keys
  colapsan en `""`). Probar **siempre los tres objetos y volver al primero**, no sólo el default;
  contrastar contra `by-object/{objeto}/` por API, que responde bien. Workaround: recargar la
  página entera.
- **Sobrecosto por restricción vs `/porque`**: pueden contradecirse para el mismo pedido, porque
  `/porque` usa `costo_incremental_usd_tn` (vacío en el paquete real → "no aplica") y el Cost
  Explorer cae a `costo_unitario_sin_restriccion` de `extra`. Verificar la coherencia haciendo clic
  en el link `?pedido=` de la tabla de restricciones.
- El panel lateral de eventos pide siempre `limit=50&offset=0` y no expone controles de página:
  con más de 50 cargos sólo se ven los 50 más caros.

## Datos y valores esperados del dataset de ejemplo

- `datos_ejemplo/paquete_auditoria_E-00-R0.zip` es el paquete importable; regenerarlo con
  `python3 datos_ejemplo/generar_ejemplo.py` si no está.
- Regla contable: `costo total (caja) = USD 57.180` (8 cargos `CAJA`) y `economico USD 3.500`
  informado aparte; si el total da 60.680 la regla está rota.
- `/corridas/E-00-R0/porque` con `P-0001`: sobrecosto de la restricción = 7 usd/tn
  (elegida 91 − más barata no factible 84).
- `P-0002` es el pedido que tiene los arcos `ESPERA_PORTACONTENEDOR` / `ESPERA_POSICION` con
  `duracion_esperada_horas = -1`, que deben mostrarse como "no aplica".

## Armar paquetes inválidos para probar el rechazo

```bash
mkdir -p /tmp/mut && cp datos_ejemplo/E-00-R0/* /tmp/mut/
rm /tmp/mut/manifiesto_auditoria_E-00-R0.json   # → "el paquete no trae manifiesto_..."
# o borrar una columna declarada en el esquema:
#   → "costos_eventos.csv: faltan columnas tipo_contable"
(cd /tmp/mut && zip -q /tmp/paquete_invalido.zip *)
```

La validación corta en el primer error: el manifiesto faltante enmascara los errores de columnas,
así que conviene armar un zip por tipo de error.

## Subir archivos desde Chrome sin usar el diálogo nativo

El diálogo de archivos de KDE se maneja bien escribiendo la ruta absoluta con `ctrl+l` y Enter
después de hacer click en el `input[type=file]`.

## Descargas

Los botones de "Exportar tablas" bajan a `~/Downloads`. El export filtrado ya incluye el filtro en
el nombre (`E-00-R0_costos_tipo_contable-caja.csv`), pero conviene igual verificar el contenido con
`csv.DictReader` (filas, `tipo_contable` único, suma de `importe_usd`) y no confiar en el nombre;
en versiones anteriores ambos exports se llamaban `E-00-R0_costos.csv` y el segundo quedaba como
`E-00-R0_costos (1).csv`.

## Devin Secrets Needed

Ninguno: la app no tiene autenticación y todo corre en localhost.
