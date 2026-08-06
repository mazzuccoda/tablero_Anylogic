# MOD v3.3 — Flujo físico y almacenaje

Qué se implementó, con qué reglas y qué se apartó del MOD porque los datos reales no lo sostienen.
Los números de esta nota son de `E-00-R0` (`datos_ejemplo/E-00-R0/Ejemplo_real.zip`), medidos contra
la base, no estimados.

## Pantalla

`/corridas/{run_id}/flujo`: cintas del flujo físico, etapa física con toneladas y costo, almacenaje
por producto, almacenaje por depósito (flujo + costo + decisión + stock diario) y trazabilidad de
lote.

## Endpoints

| Endpoint | Qué contesta |
|---|---|
| `GET /simulation-runs/{id}/costs/cintas/` | toneladas y costo por etapa física, cintas del sankey |
| `GET /simulation-runs/{id}/almacenamiento/por-producto/` | ingresos, stock, egresos, días y costo por producto |
| `GET /simulation-runs/{id}/almacenamiento/depositos/` | sitios con stock, para los chips del selector |
| `GET /simulation-runs/{id}/depositos/{ubicacion}/flujo-y-decision/` | flujo, costo y motivo de decisión de un depósito |
| `GET /simulation-runs/{id}/depositos/{ubicacion}/stock-diario/` | stock físico día a día por producto |
| `GET /simulation-runs/{id}/almacenamiento/top-lotes/` | ranking de lotes por costo, días o toneladas |
| `GET /simulation-runs/{id}/lotes/{id_lote}/recorrido/` | recorrido físico del lote y su costo |

Todos comparten `FiltrosCostos` y contestan 409 en una corrida de barrido, igual que el resto del
Cost Explorer: un panel en cero sería peor que no tener la pantalla.

## Decisiones

### El almacenaje no es un arco

`ejecucion_arcos` solo registra movimientos. El almacenaje vive en `costos_eventos` con
`categoria = ALMACENAMIENTO` y se publica aparte (`almacenamiento_excluido_usd`), nunca como cinta.
La reconciliación cierra exacto:

```
etapas 4.427.814,7606 + almacenaje 1.332.429,4212 = 5.760.244,1818 = total CAJA
```

### El costo de la etapa no se une por id contra los arcos

Un cargo de contenedor (THC, terminal, despachante) matchea cuatro o cinco arcos del mismo
contenedor: unir por `id_contenedor` multiplicaría el importe. Las toneladas salen de los arcos y el
importe de `costos_eventos` clasificado por `categoria` —el mismo mapa que usa el waterfall—.

Consecuencia: hay etapas con toneladas y sin costo (las esperas) y etapas con costo y sin toneladas
(THC, despachante). Ninguna de las dos se rellena con cero.

### Las cintas solo dibujan producto entre sitios distintos

Se dibujan `PLANTA_DEPOSITO`, `CROSS_DOCK`, `DEPOSITO_DEPOSITO` y
`ORIGEN_TERMINAL_CONTENEDOR_CARGADO` con `origen != destino`. Quedan afuera, con su tonelaje
declarado en `tipos_arco_no_dibujados`:

- los arcos de nodo (`CARGA_CONSOLIDACION`, `DESCARGA_TERMINAL`, `CONSOLIDACION_TERMINAL`,
  `ESPERA_POSICION`), que son auto-loops;
- el retiro de contenedor vacío y la espera de portacontenedor, que van de terminal a depósito y
  crearían un ciclo `depósito → terminal → depósito` que un sankey no puede representar.

El paquete real trae nueve `tipo_arco`; `DEPOSITO_DEPOSITO` está mapeado pero nunca apareció.

### Los egresos de un depósito salen de los arcos

`snapshot_inventario.egresos_dia_tn` viene en cero en los cinco depósitos (solo `PLANTA` lo
escribe), pero el stock baja. El egreso se deriva de `CARGA_CONSOLIDACION` con `origen` = depósito:

```
RUTA9 16.144,34 · DODERO 3.654,70 · BOREAS 907,70 · FRINOA 431,50 · NORRY 229,40 tn
```

`ingresos_dia_tn` sí coincide con los arcos que entran, así que se usa tal cual y sirve de control
(la respuesta publica también `ingresos_tn_en_arcos`).

### La vista por producto mira solo los sitios `tipo_ubicacion = DEPOSITO`

`PLANTA` guarda producto y no cobra almacenaje: sumarla inflaría el stock promedio y los días en
depósito. Por eso ACEITE aparece con `costo_almacenaje_usd = null`: su stock está en PLANTA. El
1,33 M de almacenaje es JUGO (965.103,44) más CÁSCARA (367.325,98).

### Días en depósito por ley de Little

```
días promedio = suma del stock físico diario / toneladas ingresadas
```

No es el promedio de `dias_stock_promedio` de AnyLogic, que es otra medida.

### El descuadre contra `snapshot_inventario` se publica

`snapshot_inventario.costo_almacenaje_dia_usd` suma 1.346.239,033 contra 1.332.429,4212 de
`costos_eventos` (1 %). La fuente de importes sigue siendo `costos_eventos` (ADR-T04) y la
diferencia se muestra en la pantalla en vez de taparse.

### `origen_stock = DEPOSITO` no es un depósito

Son 1.443 filas del pseudo-motivo `TRANSFERENCIA_DEPOSITO_DEPOSITO` con `orden_ranking = 0`. No
entra al ranking de decisiones de un depósito concreto porque contaminaría el promedio.

## Responsive

La pantalla se usa a 375 px: el flujo Ingresos → Stock → Egresos pasa a una columna con la flecha
rotada 90°, las tablas van en `overflow-x-auto`, los chips de depósito tienen área táctil de 44 px y
el color por producto es el mismo en el sankey, en las barras y en la serie diaria.
