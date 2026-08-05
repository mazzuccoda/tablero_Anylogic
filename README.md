# Tablero AnyLogic

Plataforma web que importa los resultados que ya produce el modelo de AnyLogic
(`mazzuccoda/Anylogic_log_arg_2026`, ADR-064) y los muestra en un dashboard navegable fuera del
modelo. Implementa el MVP definido en [`docs/MOD_Tablero_AnyLogic_v2_MVP.md`](docs/MOD_Tablero_AnyLogic_v2_MVP.md)
(fases 0 a 3).

Responde dos preguntas:

- **¿Cómo está funcionando la red?** — servicio, costos, capacidad, inventario.
- **¿Qué la está limitando?** — alternativas más baratas que no se pudieron usar, motivos de
  descarte y esperas físicas. Es la vista `/orders/{codigo_pedido}/why/`.

## Contrato de datos

El contrato **es el que publica AnyLogic**, no un esquema propio (ADR-T01): el importador lee
`esquema_auditoria.json` (columnas y clave de cada tabla) y `manifiesto_auditoria_<run_id>.json`
(conteo de filas y `version_esquema`) del propio paquete antes de asumir ninguna columna.

| Archivo | Grano | Clave |
|---|---|---|
| `decisiones_alternativas.csv` | una alternativa evaluada por ronda | `run_id`, `id_alternativa` |
| `asignaciones_elegidas.csv` | una asignación ejecutada | `run_id`, `id_asignacion` |
| `ejecucion_arcos.csv` | un movimiento o espera física terminada | `run_id`, `id_evento_arco` |
| `costos_eventos.csv` | un cargo devengado | `run_id`, `id_costo` |
| `snapshot_inventario.csv` | día, ubicación y producto | `run_id`, `dia`, `ubicacion`, `producto` |
| `capacidad_por_dia.csv` | día, recurso y ubicación | `run_id`, `dia`, `tipo_recurso`, `ubicacion` |

`kpis_por_corrida.csv` es lo único que existe para las corridas de un barrido, que se ejecuta con
`nivelAuditoriaRed = DESACTIVADA`. El tablero lo dice explícitamente en vez de mostrar una vista
vacía.

Tres reglas que vienen del modelo y que el código respeta:

1. Los importes se suman **sólo** desde `costos_eventos` y **sólo** con `tipo_contable = CAJA`
   (ADR-T04). El `ECONOMICO` es costo de oportunidad y se informa aparte.
2. Un campo vacío es un dato que el modelo **no produce**: se guarda como `NULL` y se muestra como
   "sin dato", nunca como cero.
3. `duracion_esperada_horas` negativa en `ejecucion_arcos` significa "no aplica" (esperar un
   portacontenedor o una posición no tiene techo físico), no un dato faltante.

## Levantar el stack

```bash
cp .env.example .env      # completar POSTGRES_PASSWORD y DJANGO_SECRET_KEY
docker compose up -d --build
```

- Tablero: <http://localhost:3000>
- API: <http://localhost:8000/api/v1/>
- Admin de Django: <http://localhost:8000/admin/>

Desde Portainer: *Stacks → Add stack → Repository*, apuntando a este repositorio, y cargar las
mismas variables en el editor de variables de entorno del stack.

### Detras de un proxy (nginx, Traefik, Cloudflare)

Un paquete real es grande y la importacion es sincronica: el `Ejemplo_real.zip` de `E-00-R0`
(2,7 MB comprimidos, 151.368 filas) tarda unos 30 s contra PostgreSQL. Si el proxy corta antes,
el navegador muestra un 502/504 (o el HTML de error del proxy) aunque el backend siga trabajando.
Con nginx alcanza con:

```nginx
client_max_body_size 200m;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
```

Datos de ejemplo (corrida `E-00-R0` y un barrido de cuatro corridas):

```bash
docker compose exec backend python manage.py cargar_ejemplo
```

## Desarrollo sin Docker

```bash
# backend (usa SQLite si no hay POSTGRES_HOST)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py cargar_ejemplo
.venv/bin/python manage.py runserver

# frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev
```

Pruebas y lint:

```bash
cd backend && .venv/bin/python -m pytest && .venv/bin/ruff check .
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Endpoints

```http
GET    /api/v1/scenarios/
GET    /api/v1/simulation-runs/
POST   /api/v1/imports/upload/            # .zip del paquete o kpis_por_corrida.csv
GET    /api/v1/imports/{id}/

GET    /api/v1/simulation-runs/{run_id}/dashboard/
GET    /api/v1/simulation-runs/{run_id}/inventory/
GET    /api/v1/simulation-runs/{run_id}/costs/
GET    /api/v1/simulation-runs/{run_id}/capacity/
GET    /api/v1/simulation-runs/{run_id}/decisions/
GET    /api/v1/simulation-runs/{run_id}/export/{tabla}/    # CSV filtrado

GET    /api/v1/orders/{codigo_pedido}/why/?run_id=...      # CU-04
POST   /api/v1/comparisons/                                # CU-05
GET    /api/v1/sweep-kpis/
```

`{run_id}` acepta tanto el id numérico como el `run_id` del modelo (`E-00-R0`).

## Estructura

```
backend/            Django + DRF
  apps/core/        modelo de datos (secciones 6.1 y 6.2 del MOD)
  apps/ingest/      lectura del esquema publicado e importadores
  apps/dashboard/   agregados, vista "por que", comparador, exportación
  tests/            importación, validaciones y endpoints
frontend/           Next.js + TypeScript + Tailwind + ECharts + TanStack Table
datos_ejemplo/      corrida E-00-R0 y kpis_por_corrida.csv de referencia
docs/               MOD v2.0 y notas de implementación
```

## Fuera de esta versión

Nextcloud, Celery/Redis, multiusuario, animación temporal, estadística de réplicas, reportes PDF y
recepción directa por API desde AnyLogic quedan diferidos con la condición que los activa: §14 del
MOD. La condición común es evidencia de necesidad real de uso, no anticipación.
