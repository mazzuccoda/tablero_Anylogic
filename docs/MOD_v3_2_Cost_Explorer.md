# MOD v3.2 — Cost Explorer con costeo por objeto de costo

Revision del MOD v3.1. Cambia solo lo que hizo falta cambiar despues de medir el paquete real
`E-00-R0` (`datos_ejemplo/E-00-R0/Ejemplo_real.zip`: 105.270 filas CAJA por USD 5.760.244 y 1.095
filas ECONOMICO por USD 435.479). Todo numero que aparece abajo esta calculado sobre ese paquete.

---

# A. Respuesta corta a la pregunta del USD/tn

**Si, se puede, y tu razonamiento es el correcto.** Yo lo habia planteado mal: dije que USD/tn no se
podia calcular porque las unidades no se pueden sumar (`USD_TN_DIA` + `USD_CONTENEDOR` + `USD_VIAJE`).
Eso sigue siendo cierto para las *cantidades*, pero es irrelevante para el USD/tn, porque el
denominador no sale de `cantidad`: sale del **objeto de costo** (el lote, el contenedor, el pedido),
y las toneladas de cada objeto estan en el paquete.

Verificado sobre el paquete real:

1. **Las toneladas del lote estan dos veces y coinciden exactamente.** `IN_DEPOSITO` viene en
   `USD_TN` con `cantidad` = toneladas ingresadas, y `ejecucion_arcos` trae el arco
   `PLANTA_DEPOSITO` con `toneladas`. Sobre los 145 lotes que ingresaron a deposito, la diferencia
   entre las dos fuentes es **0 en los 145** (tn total ingresada: 21.039).
2. **Las toneladas del contenedor estan siempre.** Los 1.974 contenedores con costo tienen
   toneladas en el arco `CARGA_CONSOLIDACION`. Ejemplo real: contenedor `P00002-C1.0`,
   USD 1.261,10 sobre 22,44 tn = **56,20 USD/tn**.
3. **Cada contenedor pertenece a un solo pedido.** 1.978 contenedores, **cero** con mas de un
   pedido. O sea que todo el costo de contenedor (THC, terminal, despachante, consolidacion,
   round trip: 37,7 % del CAJA) es atribuible al pedido **sin prorratear nada**.
4. **La cadena del lote se puede seguir entera.** Ejemplo real del lote `30`: dia 147 entra con
   flete (`USD_VIAJE`, 300 USD por viaje) y `IN_DEPOSITO` (25 tn a 2,50 USD/tn), acumula
   almacenamiento a 0,48 USD/tn/dia y despues egresa. Total del lote: USD 21.809 de
   almacenamiento + USD 2.700 de flete + USD 519 de ingreso sobre 207,5 tn ingresadas.

Entonces el USD/tn se define **por nivel**, cada uno con su denominador fisico declarado, y se
agrega hacia arriba ponderado por toneladas. Ningun nivel divide por una suma de unidades mezcladas.

## Lo unico que NO sale exacto, y por que

El almacenamiento (23 % del costo CAJA, USD 1.332.429) se devenga **por dia sobre el lote**, no por
pedido. Aplicando la regla fisica que planteas —cada tonelada retirada pagó los dias que estuvo
guardada— se atribuye asi:

```text
almacenamiento_atribuido(pedido) = Σ  tn_retiradas × (dia_retiro − dia_ingreso_lote) × tarifa
                                   sobre los arcos CARGA_CONSOLIDACION del pedido
```

Resultado medido: **USD 719.641 (54,0 %)** del almacenamiento queda atribuido a pedidos, y
**USD 612.788 (46,0 %)** no. El resto no es un problema de datos: son toneladas-dia de producto que
entro al deposito y **no se despacho en la campaña** (2.435.418 tn·dia facturadas contra 1.340.446
tn·dia consumidas por retiros, o sea el 55 %). Ese remanente es un numero valioso por si mismo —
almacenamiento pagado por stock que no genero venta— y va como linea propia:

```text
ALMACENAMIENTO_DE_STOCK_NO_DESPACHADO   612.789 USD
```

No se prorratea entre pedidos, porque prorratearlo seria cobrarle a un pedido el costo de una
tonelada que nunca se llevo.

---

# B. Modelo de costeo (reemplaza §7 del v3.1)

## B.1 Objetos de costo

Cada fila de `costos_eventos` cuelga de un objeto de costo, que se deduce de `alcance` (poblado al
100 % en el paquete real: LOTE 94.212 filas, CONTENEDOR 10.430, PEDIDO 628):

| objeto | id | toneladas del objeto | fuente de las toneladas |
|---|---|---|---|
| LOTE | `id_lote` | tn ingresadas | `cantidad` de `IN_DEPOSITO` (= `toneladas` del arco `PLANTA_DEPOSITO`) |
| CONTENEDOR | `id_contenedor` | tn cargadas | `toneladas` del arco `CARGA_CONSOLIDACION` |
| PEDIDO | `codigo_pedido` | tn entregadas | `toneladas_entregadas` de `asignaciones_elegidas` |
| RED | corrida | tn entregadas | suma de `toneladas_entregadas` (30.315 tn) |

Los 8 lotes (de 184) sin ninguna fuente de toneladas quedan con toneladas `null` y su USD/tn se
muestra "sin dato". No se les pone 0 ni se los excluye del total.

## B.2 Metricas por nivel

```python
usd_tn(objeto) = importe_usd_total(objeto) / toneladas(objeto)      # null si toneladas es null o 0
```

- **Lote**: `usd_tn_lote`, y ademas `usd_tn_dia` (= `tarifa` de almacenamiento) y `dias_en_deposito`.
- **Contenedor**: `usd_tn_contenedor` y `usd_contenedor`.
- **Pedido**: `usd_tn_pedido`, con las tres capas separadas (ver B.3).
- **Etapa / producto / circuito / ubicacion / arco**: `importe_usd` exacto, y `usd_tn` con la
  **base declarada en la respuesta**, porque cada etapa tiene su propia base fisica:

```json
{ "etapa": "ALMACENAMIENTO", "importe_usd": 1332429,
  "base": { "nombre": "tn_ingresadas_a_deposito", "valor": 21039 }, "usd_tn": 63.33 }
{ "etapa": "THC", "importe_usd": 371120,
  "base": { "nombre": "tn_en_contenedores", "valor": 30557 }, "usd_tn": 12.15 }
```

Nunca se publica un `usd_tn` sin su `base`. El USD/tn de portada de la red es
`costo_caja_total / tn_entregadas` = 5.760.244 / 30.315 = **190,02 USD/tn**, y no es la suma de los
USD/tn por etapa (cada etapa tiene otra base): el waterfall se hace en USD, no en USD/tn.

`cantidad` se sigue sumando solo dentro de una misma `unidad`, y la unidad viaja en la respuesta.
En este paquete cada categoria tiene una sola unidad, asi que el corte por categoria es seguro:

```text
ALMACENAMIENTO USD_TN_DIA | IN/OUT_DEPOSITO USD_TN | FLETE_PRODUCTO USD_VIAJE
THC, COSTO_TERMINAL, DESPACHANTE, CONSOLIDACION, ROUND_TRIP, CROSS_DOCK USD_CONTENEDOR
```

## B.3 Costo por pedido: tres capas explicitas

Las capas no se solapan (medido: todos los cargos con `id_contenedor` ya traen `codigo_pedido`, asi
que la capa de contenedor es exacta y esta dentro de la directa):

```text
capa                                            USD          %      regla
directo                                   3.113.612       54,1 %   el cargo trae codigo_pedido
                                                                   (incluye todo el costo de contenedor)
entrada del lote atribuida                1.091.410       18,9 %   flete planta-deposito + IN_DEPOSITO
                                                                   × (tn retiradas / tn ingresadas del lote)
almacenamiento atribuido                    719.641       12,5 %   tn retiradas × dias en deposito × tarifa
--------------------------------------------------------------------
atribuido al pedido                       4.924.663       85,5 %
almacenamiento de stock no despachado       612.788       10,6 %   linea propia, no se prorratea
entrada de stock no despachado              222.792        3,9 %   linea propia, no se prorratea
--------------------------------------------------------------------
total CAJA                                5.760.244      100,0 %
```

O sea: **el 85,5 % del costo CAJA queda atribuido a un pedido con reglas fisicas** (ninguna
proporcion inventada), y el 14,5 % restante es costo de producto que entro al deposito y no se
despacho en la campaña, que es informacion, no un agujero.

El frontend muestra siempre las capas, y el USD/tn del pedido aclara sobre que capa se calculo. Un
pedido nunca recibe una porcion del `ALMACENAMIENTO_DE_STOCK_NO_DESPACHADO`.

## B.4 Reconciliacion por dimension (reemplaza §4.1 y §9.4)

No hay un unico `estado: OK|WARNING`. La reconciliacion declara por dimension si es exacta o
parcial, con el importe que queda afuera:

```json
{
  "total_caja_usd": 5760244.18,
  "dimensiones": {
    "etapa":      { "suma": 5760244.18, "diferencia": 0, "estado": "EXACTA" },
    "producto":   { "suma": 5760244.18, "diferencia": 0, "estado": "EXACTA" },
    "circuito":   { "suma": 5760244.18, "diferencia": 0, "estado": "EXACTA" },
    "ubicacion":  { "suma": 5760244.18, "diferencia": 0, "estado": "EXACTA" },
    "pedido":     { "suma_directa": 3113612.00, "suma_atribuida": 4924663.00,
                    "diferencia": 835580.00, "estado": "PARCIAL",
                    "motivo": "costo de producto que entro al deposito y no se despacho en la campania" }
  },
  "etapa_no_clasificada_usd": 0
}
```

`etapa`, `producto`, `circuito`, `origen`, `destino`, `sitio`, `categoria`, `alcance` y `unidad`
estan poblados en el **100 %** del importe en el paquete real: esas cinco dimensiones reconcilian
exacto y una diferencia distinta de cero es un bug, no un dato faltante. Una prueba lo fija.

---

# C. Clasificacion de etapas (reemplaza §8 del v3.1)

`categoria` esta poblada en el 100 % del importe y tiene 10 valores, asi que la cascada de siete
niveles no hace falta: alcanza un mapa directo, y el resto queda como fallback.

```python
ETAPA_POR_CATEGORIA = {
    "FLETE_PRODUCTO": TRANSFERENCIA_PLANTA_DEPOSITO,   # 2.209.875
    "ALMACENAMIENTO": ALMACENAMIENTO,                  # 1.332.429
    "ROUND_TRIP": RETIRO_CONTENEDOR,                   #   834.400
    "CONSOLIDACION": CONSOLIDACION,                    #   511.485
    "THC": THC,                                        #   371.120
    "DESPACHANTE": DESPACHANTE,                        #   234.960
    "COSTO_TERMINAL": TERMINAL,                        #   158.970
    "IN_DEPOSITO": INGRESO_DEPOSITO,                   #    45.202
    "OUT_DEPOSITO": EGRESO_DEPOSITO,                   #    42.642
    "CROSS_DOCK": CROSS_DOCK,                          #    19.160
    "OPORTUNIDAD_FRIO": OPORTUNIDAD,                   #   435.479 (ECONOMICO)
}
```

Requisitos:

- una prueba que **falla cuando aparece una categoria nueva** (es la señal de que el modelo cambio);
- el importe que caiga en `ETAPA_NO_CLASIFICADA` se publica en la reconciliacion;
- las etapas del v3.1 que este paquete no escribe (PRODUCCION, MARITIMO, ESPERA, DEMORA, PENALIDAD)
  no se crean vacias: se agregan cuando el modelo las emita.

---

# D. Nodo y arco no son lo mismo (reemplaza §9.5)

Armar el arco como `origen → destino` mezcla dos cosas. En el paquete real hay 22 pares y los cinco
mas grandes son auto-loops: `RUTA9 → RUTA9` (42.604 filas), `NORRY → NORRY` (23.114),
`BOREAS → BOREAS` (12.031), `FRINOA → FRINOA` (9.638), `DODERO → DODERO` (5.803). Son costos de
nodo (almacenamiento), no de tramo.

```python
tipo_geografia = "NODO" if origen == destino else "ARCO"   # "NO_CLASIFICADO" si falta uno
```

El desglose de red se parte en **costos de nodo** (deposito, planta, terminal) y **costos de arco**
(tramos). Sin esa separacion el ranking de "arcos mas caros" queda dominado por el almacenamiento y
la pregunta "que nodo genero mas costo" no se puede contestar.

---

# E. Sobrecosto por restriccion (sube de PR-06 a PR-02)

Es la pregunta central del proyecto y hoy no funciona con datos reales: con el paquete real,
`sobrecosto_de_la_restriccion_usd_tn` devuelve `null` en los pedidos que probe, aunque las
alternativas descartadas esten ahi (P00633: 288 alternativas evaluadas, 286 no factibles).

Definicion explicita, con columnas reales de `decisiones_alternativas`:

```text
elegida      = alternativa con resultado_ejecucion elegido para la decision
candidata    = alternativa con es_mas_barata_no_factible = true (o la de menor
               costo_end_to_end_usd_tn entre las no factibles)
sobrecosto_usd_tn  = costo_end_to_end_usd_tn(elegida) − costo_end_to_end_usd_tn(candidata)
sobrecosto_total   = sobrecosto_usd_tn × toneladas_tomadas(elegida)
restriccion        = codigo_motivo (+ detalle_motivo) de la candidata
```

Con pruebas para: sin alternativa factible, sin no-factible mas barata, sobrecosto negativo, pedido
sin asignacion, toneladas nulas o cero. Y un ranking `restriccion → sobrecosto total` que es,
literalmente, "cuanto costo la restriccion" para toda la campaña.

---

# F. Rendimiento y entrega (ajusta §18)

- Eventos **paginados server-side** (`limit`/`offset`, orden estable, `total` aparte). Hoy
  `/costs/` devuelve 5.000 filas y 2,6 MB en una sola respuesta con el paquete real.
- Export CSV por streaming (`StreamingHttpResponse`), sin cargar 105.000 filas en memoria.
- Agregados por ORM (`values().annotate()`), sin N+1. Medido: los agregados sobre 105.000 filas
  responden en decimas de segundo, asi que **no hay cache ni tablas materializadas** en esta fase.
- Cada respuesta trae `filtros_aplicados`, `filas_consideradas` e `importe_considerado`, para que un
  numero copiado a una presentacion se pueda reproducir despues.
- Los filtros viven en el query string del frontend (`?producto=JUGO&etapa=ALMACENAMIENTO&
  dia_desde=90`), asi una vista es un link compartible.
- Corrida BARRIDO: el Cost Explorer responde con el mensaje explicito de "sin tablas de auditoria",
  no con paneles en cero.

---

# G. Roadmap ajustado (reemplaza §15)

| PR | contenido |
|---|---|
| PR-01 | modulo `cost_explorer`, filtros reutilizables, clasificacion por categoria + prueba de categoria desconocida, objetos de costo y sus toneladas, resumen, reconciliacion por dimension |
| PR-02 | desglose por etapa / producto / circuito / ubicacion **y sobrecosto por restriccion** |
| PR-03 | nodo vs arco, eventos paginados, export CSV por streaming |
| PR-04 | frontend: tarjetas, waterfall en USD, Pareto por etapa, filtros en URL |
| PR-05 | tabla jerarquica, panel lateral, drill-down hasta evento, USD/tn por lote y por contenedor |
| PR-06 | costo por pedido con las tres capas + `ALMACENAMIENTO_DE_STOCK_NO_DESPACHADO` |
| PR-07 | comparador de costos entre corridas |

Cada PR cierra con la salida de reconciliacion medida contra `E-00-R0` real en la descripcion.

---

# H. Criterios de aceptacion (ajusta §20)

Se mantienen los 15 del v3.1, con estos cambios:

1. el costo total reconcilia **exacto** en etapa, producto, circuito, ubicacion, categoria y
   alcance, y **declarado como parcial con motivo e importe** en pedido, asignacion y contenedor;
2. todo `usd_tn` publicado viene con su `base` (nombre y valor);
3. existe USD/tn por lote y por contenedor, trazable hasta los eventos que lo componen;
4. el almacenamiento de stock no despachado se muestra como linea propia y no se prorratea;
5. existe el ranking de restricciones por sobrecosto total;
6. una categoria de costo nueva rompe una prueba en vez de caer en "OTROS".
