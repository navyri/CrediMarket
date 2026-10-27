# CrediMarket — Parte 2

Microservicios, mensajería, Redis y MLOps (Universidad EIA).

> Contexto: los datos y las operaciones de crédito son sintéticos y académicos. No constituyen una política financiera aplicable a personas reales.

## Integrantes y responsabilidades

Grupo de **un (1) integrante** (máximo permitido: 4, §2.1). Por política de privacidad (P2-DEC-006), solo se publica el nombre de pila.

| Integrante | Responsabilidades principales |
|---|---|
| **Mariana** | Todos los frentes de trabajo: servicios Productos/Inventario + Redis; Clientes + seguridad + frontend; Préstamos + broker; datos + modelo + MLOps; documentación y sustentación. |

> Nota de trazabilidad (CON-003): el enunciado (§2.2, §14, §15.2 c8) prevé grupos de hasta 4 integrantes con contribuciones visibles de los cuatro; este grupo tiene un solo miembro, por lo que el historial Git contiene contribuciones reales de una única integrante. No se han generado autorías adicionales.

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
