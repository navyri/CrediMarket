# Informe de Redis y desempeño (entregable 6)

Base: §6 (caché obligatoria y evidencia exigida) y §15.2 c5. Todas las cifras de
este informe provienen de corridas reproducibles contra el Compose real en una
máquina Windows de desarrollo (todo el sistema en el mismo host: las latencias
incluyen el loopback HTTP + JWT; no son latencias de red entre máquinas).

Comandos que regeneran los datos:

```bash
python scripts/medir_cache.py                    # MISS/HIT + carga + invalidación
docker compose stop redis
python scripts/medir_cache.py --sin-redis        # camino de fallback (BD)
docker compose start redis
python scripts/aceptacion/ejecutar_todas.py      # casos 08 y 09 (Redis) + el resto
```

## 1. Diseño de la caché (lo que se midió)

| Aspecto | Decisión |
|---|---|
| Patrón | cache-aside: `GET clave` → miss → BD → `SET` con TTL |
| Clave | `productos:v1:{producto_id}` (`productos` + versión `v1` + id) |
| TTL de la caché | 60 s (`CACHE_TTL_SEG`, configurable) |
| Invalidación | `DEL` de la clave **después** del commit del `PATCH`/`DELETE` + borrado del fallback local |
| Fallback en memoria | TTL 5 s, solo cuando Redis no responde; nunca sustituye a la BD |
| Timeouts de conexión | `socket_connect_timeout=1`, `socket_timeout=1` |
| Cortacircuitos | Tras el primer fallo no se toca Redis durante 5 s (`CACHE_FAIL_FAST_SEG`); al vencer se reintenta y, si responde, se cierra |
| Fuente de verdad | La cotización oficial y la deduplicación viven en PostgreSQL, jamás en Redis |

Condición de dato desactualizado documentada: como máximo el TTL (60 s) si la
invalidación no llegó a ejecutarse por una caída simultánea, o 5 s de datos
servidos por el fallback en memoria durante una indisponibilidad.

## 2. Mediciones con Redis disponible

Corrida `python scripts/medir_cache.py --lecturas 40`
(evidencia: `docs/evidencias/mediciones_cache.json`):

| Escenario | n | mín (ms) | p50 (ms) | p95 (ms) | máx (ms) |
|---|---|---|---|---|---|
| MISS (tras `FLUSHDB`, 1.ª lectura) | 1 | 6,40 | — | — | — |
| HIT (lecturas consecutivas) | 40 | 3,40 | **14,15** | 27,11 | 28,00 |
| Latencia interna del GET sobre Redis | 83 | — | **0,26** | 0,463 | — |

- `hit_rate` acumulado: **97,59 %** · `tasa_fallback`: **0,0 %** ·
  `errores_redis`: 0 · `invalidaciones`: 1 (la del `PATCH` de la corrida).
- La primera lectura tras vaciar la caché puebla la clave; las siguientes son
  HIT. El GET a Redis cuesta 0,26 ms (p50): el resto del tiempo de la petición
  es HTTP + validación del JWT, por eso la diferencia MISS/HIT a nivel de
  navegador se mide sobre todo en la parte que Redis sí ahorra (el acceso a
  PostgreSQL, §2.3).

### Carga sobre el listado del catálogo

| Escenario | p50 (ms) | p95 (ms) | peticiones/s |
|---|---|---|---|
| Serie secuencial (40 × `GET /productos?pagina=1&tamano=50`) | 15,29 | 30,39 | **64,0** |
| Concurrente, 20 hilos (40 peticiones) | 77,23 | 108,95 | **208,3** |

## 3. Comportamiento ante fallos

### 3.1 Ciclo completo de caída y recuperación (caso 08 de §12)

`docs/evidencias/aceptacion/caso_08.json` cubre, sobre el sistema real:

1. `FLUSHDB` → miss → lectura desde BD → **repueble con TTL** (clave presente);
2. expiración de la clave → vuelve a ser miss → repueble;
3. `docker compose stop redis` → el `GET /productos/{id}` sigue respondiendo
   **200** desde la BD (fallback) con el precio correcto;
4. `docker compose start redis` → la caché vuelve a operar (siguiente lectura
   puebla la clave) y `redis_disponible` pasa a `true`.

### 3.2 Hallazgo y corrección: espera acotada ante caída de Redis

La primera medición con Redis detenido expuso un incumplimiento del §6
(«con un tiempo de espera acotado»): **cada** petición pagaba el timeout de
conexión, no solo la primera.

| Corrida de 12 lecturas con Redis caído | mín (ms) | p50 (ms) | p95 (ms) | máx (ms) |
|---|---|---|---|---|
| Antes (sin cortacircuitos) | 3.133,60 | **4.833,59** | 6.301,29 | 10.260,95 |
| Después (con cortacircuitos) | 2,81 | **15,28** | 28,23 | 7.127,29* |

\* La única lectura lenta es la sonda que abre la ventana; las 11 restantes
responden sin tocar Redis (fallback en memoria con TTL 5 s o BD).

Corrección aplicada en `servicios/productos/app/cache.py`: cortacircuitos con
ventana de fail-fast (`CACHE_FAIL_FAST_SEG=5`). Durante la ventana los intentos
se omiten y se contabilizan como `errores_redis` (métrica de indisponibilidad);
al vencer se reintenta una vez y, si Redis responde, se reanudan las operaciones.
Prueba unitaria que lo garantiza: `test_cortacircuitos_no_reintenta_redis_durante_la_ventana_unit`.

### 3.3 Invalidación por cambio de precio (caso 09 de §12)

`PATCH /productos/{id}` 175.000 → 250.000: la versión avanza, la clave
`productos:v1:{id}` se borra (`clave_borrada: true` en la evidencia) y el
préstamo posterior cotiza al precio nuevo con la versión reciente. El navegador
nunca envía el precio (§4).

## 4. Límites de Redis (§6)

- **No** reemplaza las bases de datos de Préstamos ni de Inventario: la
  deduplicación de solicitudes y de eventos es durable en PostgreSQL
  (tabla `prestamos.idempotency_key` con `request_hash` y respuesta asociada) y
  sobrevive a la caída o al `FLUSHDB` de Redis (casos 05 y 08).
- La cotización que define el monto se lee de la fuente de verdad con su
  `version`; una caché vieja no puede fijar el precio (caso 09).
- Rate limiting: no implementado (opcional, no suma) para no confundirlo con la
  caché exigida.

## 5. Recursos consumidos

`docker stats --no-stream` con las 9 cargas levantadas y sin carga activa:

| Contenedor | CPU | Memoria | % de la máquina |
|---|---|---|---|
| `credimarket-productos-1` | 0,10 % | 85,0 MiB | 0,27 % |
| `credimarket-clientes-1` | 0,09 % | 77,9 MiB | 0,24 % |
| `credimarket-prestamos-1` | 0,23 % | 180,7 MiB | 0,57 % |
| `credimarket-inventario-1` | 0,21 % | 81,5 MiB | 0,26 % |
| `credimarket-frontend-1` (nginx) | 1,42 % | 23,3 MiB | 0,07 % |
| `credimarket-postgres-1` | 0,07 % | 39,0 MiB | 0,12 % |
| `credimarket-redis-1` | 1,76 % | 6,5 MiB | 0,02 % |
| `credimarket-rabbitmq-1` | 0,14 % | 117,8 MiB | 0,37 % |
| `credimarket-mlflow-1` | 1,04 % | 2,48 GiB | 7,95 % |

Tamaño de las imágenes construidas: frontend 74 MB · productos 343 MB ·
clientes 343 MB · inventario 344 MB · prestamos 819 MB (incluye el pipeline y
las dependencias de inferencia).

El consumo lo domina MLflow (contenedor Python con la UI y sus artefactos);
Redis aporta 6,5 MiB y es el componente que más latencia ahorra por byte
usado. En la carga concurrente de §2 el servicio de Productos sostuvo
208 peticiones/s con p95 de 109 ms sin agotar conexiones.

## 6. Evidencias asociadas

- `docs/evidencias/mediciones_cache.json` — MISS/HIT, carga e invalidación.
- `docs/evidencias/mediciones_cache_sin_redis.json` — camino de fallback.
- `docs/evidencias/aceptacion/caso_08.json` — Redis vacío/expirado/caído.
- `docs/evidencias/aceptacion/caso_09.json` — invalidación por precio.
- `docs/evidencias/p2_test_019_redis_cache.json` — hit-rate, fallback, p50/p95.
