# Estrategia de pruebas y evidencias

Diseño de P2-1.10. Base: §12 (16 pruebas de aceptación), §15.2 (rúbrica), reglas del encargo.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 1. Niveles

| Nivel | Herramienta | Alcance | Identificación |
|---|---|---|---|
| Unitario | `pytest` | lógica pura de cada servicio (máquina de estados, hashing, validaciones, reservas con BD en memoria/transaccional). **Se usan mocks aquí, declarados como tales** (`servicios/*/tests/test_*_unit.py`) | no sustituye integración |
| Integración API | `pytest` + `TestClient` + RabbitMQ/Redis/PostgreSQL reales vía Compose | endpoints completos con sus dependencias reales | `servicios/*/tests/integracion/` |
| Mensajería | scripts `scripts/pruebas/` contra Compose | publicación real, reintentos, DLQ, deduplicación, caída/recuperación | evidencia con logs |
| Aceptación (16) | `scripts/aceptacion/caso_*.py` (uno por caso de §12) | flujo extremo a extremo con backend real | un resultado por prueba P2-TEST-* |
| Frontend E2E | flujo manual documentado + capturas (§10) | navegador contra APIs reales | guía de demo |

No hay mocks en la demostración: los mocks existen solo en unitarios y están rotulados.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 2. Registro de evidencias

Cada ejecución guarda su resultado en JSON dentro de `docs/evidencias/`:

- `docs/evidencias/aceptacion/caso_NN.json` (uno por caso de §12) con los campos
  `id`, `requisito`, `esperado`, `observado`, `estado`, `detalle`, `commit` y
  `ejecutado_en`; `resultados.json` consolida la corrida (`total`, `ok`,
  `fallos`, `duracion_total_s`).
- Mediciones puntuales: `mediciones_cache.json`, `mediciones_cache_sin_redis.json`,
  `p2_test_019_redis_cache.json`, `p2_test_020_drift_simulado.json`,
  `experimentos_mlflow.json`, `ensayo_clon_limpio.json`.

El orquestador `scripts/aceptacion/ejecutar_todas.py` regenera la evidencia de los
16 casos; el estado solo puede ser `OK` cuando `observado` refleja una ejecución
real (prohibido marcar OK sin ejecutar). Los logs pesados quedan fuera del repo
(gitignored) y se cita su hash.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 3. Matriz pruebas de aceptación → casos

| §12 # | Caso | Prueba | Componente clave |
|---|---|---|---|
| 1 | Riesgo favorable con existencias | P2-TEST-001 | flujo completo + entrega |
| 2 | Solicitud rechazada | P2-TEST-002 | versión de modelo registrada, sin reserva |
| 3 | Favorable sin existencias | P2-TEST-003 | `insuficiente`, sin stock negativo |
| 4 | Dos solicitudes por la última unidad | P2-TEST-004 | concurrencia (dos clientes httpx asíncronos) |
| 5 | Misma petición y evento repetidos | P2-TEST-005 | idempotency key + `event_id` duplicado |
| 6 | Caída del consumidor o broker | P2-TEST-006 | reinicio de contenedor y reentrega |
| 7 | Cancelación y evento tardío | P2-TEST-007 | T9, log `evento_tardio_ignorado` |
| 8 | Redis vacío/expirado/caído | P2-TEST-008 | miss/hit/TTL/fallback medidos |
| 9 | Precio modificado | P2-TEST-009 | invalidación + cotización vigente |
| 10 | Modelo exportado vs API | P2-TEST-010 | equivalencia pipeline/joblib vs endpoint |
| 11 | Promoción y rollback | P2-TEST-011 | dos versiones, `modelo/info` |
| 12 | Importar CSV dos veces | P2-TEST-012 | 0 insertados/actualizados la 2.ª |
| 13 | Préstamos ajenos | P2-TEST-013 | 403 con token de otro cliente |
| 14 | Flujo desde frontend | P2-TEST-014 | navegador, datos persistidos |
| 15 | Pendiente y actualización asíncrona | P2-TEST-015 | 202 + polling hasta APROBADA |
| 16 | Formulario inválido / sesión vencida / API caída | P2-TEST-016 | mensajes y recuperación |

Extras exigidos por rúbrica (no son de §12 pero se prueban): P2-TEST-017 (outbox: caída entre
guardar y publicar), P2-TEST-018 (dead letter tras reintentos), P2-TEST-019 (mediciones Redis:
p50/p95/hit-rate/fallback), P2-TEST-020 (drift simulado y monitoreo, P2-9.4).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 4. Concurrencia e idempotencia

- Última unidad: dos `POST /prestamos` concurrentes (httpx AsyncClient + `asyncio.gather`) sobre
  stock=1 → exactamente una `APROBADA`, otra `CANCELADA_SIN_STOCK` (§12.4).
- Duplicado de evento: reentrega forzada del mismo `event_id` (reconexión) → un solo efecto en
  inventario (§12.5).
- Duplicado HTTP: misma key reprocesada → mismo `prestamo_id`; key con cuerpo distinto → 409.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 5. Reproducibilidad

- Semilla fija `SEMILLA = 42` (`ml/train/entrenar.py`) en entrenamiento y en datos de prueba.
- `scripts/aceptacion/ejecutar_todas.py` orquesta los 16 casos contra Compose y produce un
  resumen `resultados.json` (IDs, esperado/observado, duración) que alimenta `docs/evidencias/`.
- Compose es el único requisito de infraestructura (sin nube de pago, §13).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer&color=D8455C" alt=""/>
</p>
