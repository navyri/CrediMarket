# CrediMarket — Parte 2

Microservicios, mensajería, Redis y MLOps (Universidad EIA).

> Contexto: los datos y las operaciones de crédito son sintéticos y académicos. No constituyen una política financiera aplicable a personas reales.

## Integrantes y responsabilidades

| Integrante | Responsabilidades principales |
|---|---|
| _Pendiente (P2-0.6: nombres reales no disponibles aún; no se inventan)_ | |

## Arquitectura (resumen)

Cuatro microservicios de negocio: **Productos**, **Clientes**, **Préstamos** (Python, contiene el modelo ML) e **Inventario**, más frontend, broker (Kafka o RabbitMQ), Redis y MLflow como infraestructura. Detalle y contratos en `docs/`.

## Estructura

```
docs/       registro maestro, contratos, diagramas, guías
servicios/  productos, clientes, prestamos, inventario
frontend/   web
ml/         preparación, entrenamiento, exportación
pruebas/    pruebas de aceptación y evidencias
scripts/    utilidades de arranque y medición
```

## Puesta en marcha

_Pendiente (P2-2.7: docker-compose.yml)._

## Repositorio

- Rama: `main`
- Política: commits pequeños y coherentes, `git add` explícito, sin secretos ni artefactos pesados (ver `docs/P2_REGISTRO_MAESTRO.md`, P2-DEC-005).
