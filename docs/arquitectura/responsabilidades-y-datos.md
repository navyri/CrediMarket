# Responsabilidades y propiedad de datos

CrediMarket · Parte 2 · documento de diseño de la Etapa P2-1.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 1. Alcance

Cuatro microservicios de negocio (§3 del enunciado). El frontend, la base de datos, el broker,
Redis y MLflow son **infraestructura o cliente**, no servicios de negocio. No existe ni existirá un
quinto servicio de negocio; el entrenamiento es un proceso fuera de línea y el modelo lo sirve
Préstamos.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 2. Responsabilidades por servicio

| Servicio | Responsabilidades | Exclusiones explícitas |
|---|---|---|
| **Productos** | CRUD de productos (crear, consultar, actualizar, desactivar); precio, categoría y versión del producto; cotización vigente; caché Redis *cache-aside* del catálogo. | No administra existencias ni decide préstamos. |
| **Clientes** | Registro, consulta y actualización de clientes; información financiera y laboral; importación masiva por CSV con resumen por fila. | No ejecuta el modelo ni modifica inventario. |
| **Préstamos** | Recibir solicitudes, reunir datos por API, ejecutar el pipeline de riesgo, aplicar reglas de negocio, gestionar la máquina de estados, coordinar reservas/entregas/cancelaciones por mensajes, idempotencia HTTP, promoción y servicio del modelo ML. | No lee existencias directamente ni escribe en las tablas de otros servicios. |
| **Inventario** | Existencias, entradas, reservas atómicas, confirmación de salida, liberación y vencimiento de reservas, movimientos. | No calcula riesgo ni conoce datos financieros del cliente. |

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 3. Propiedad de datos

Cada servicio es dueño exclusivo de sus entidades. **Ningún servicio consulta las tablas de otro**
(§3, reglas de arquitectura): la única vía permitida es la API pública del dueño o un mensaje del
broker.

| Servicio | Entidades propias (propietario de las tablas) | Identificadores que almacena |
|---|---|---|
| Productos | `producto` | `producto_id` propio; conoce solo su `producto_id` |
| Clientes | `cliente`, `usuario` (cuentas y roles) | `cliente_id` propio; conoce solo su `cliente_id` |
| Préstamos | `prestamo`, `solicitud_idempotente` (idempotencia HTTP), `outbox`, `evento_procesado` (deduplicación), `metrica_inferencia` (monitoreo) | `prestamo_id` propio; almacena `cliente_id` y `producto_id` **como referencia recibida por API**, no como consulta a tablas ajenas |
| Inventario | `existencia`, `reserva`, `movimiento`, `outbox`, `evento_procesado` (deduplicación) | `producto_id` **como referencia** (clave externa lógica de la API de Productos); no consulta `producto` |

Reglas de separación:

1. Las claves ajenas (`cliente_id`, `producto_id`) se guardan como **referencias opacas** recibidas
   por API o mensaje. Validar que existen implica llamar a la API del dueño, nunca un `JOIN` entre
   bases.
2. Una única instancia física de base de datos está permitida (§3), **siempre** con esquemas
   separados (`productos`, `clientes`, `prestamos`, `inventario`) y credenciales por servicio que
   solo ven su esquema. La decisión de motor y topología se fija en P2-1.2/P2-2.3.
3. Redis y el broker no son fuente de verdad: la deduplicación y los estados viven en la base del
   servicio dueño.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 4. Vías de comunicación autorizadas

| Desde | Hacia | Vía | Uso |
|---|---|---|---|
| Préstamos | Clientes | REST `GET` de cliente | Recolección de datos de la solicitud |
| Préstamos | Productos | REST de cotización/versión | Precio vigente; se persiste `precio` + `version` usados |
| Préstamos | Inventario | **Broker** (comandos `prestamo.reserva.solicitada`, `prestamo.reserva.cancelada`) | Reserva y liberación |
| Inventario | Préstamos | **Broker** (eventos `inventario.reserva.reservada`, `inventario.reserva.insuficiente`, `inventario.reserva.liberada`, `inventario.reserva.vencida`, `inventario.salida.confirmada`) | Resultado de la reserva, vencimiento y entrega |
| Frontend | los 4 servicios | REST pública autorizada (JWT + roles) | Todas las pantallas |
| MLflow | — | infraestructura; Préstamos/entrenamiento hablan con él como cliente | Tracking y artefactos |

Direcciones prohibidas: Frontend → BD/Redis/broker/MLflow; cualquier servicio → tablas de otro;
Inventario → cualquier dato financiero del cliente (los mensajes hacia Inventario solo llevan
`prestamo_id`, `producto_id`, `cantidad`, `plazo` operativo y correlación).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 5. Infraestructura (no cuenta como servicios de negocio)

Broker **RabbitMQ** (P2-DEC-011) · Redis (solo Productos) · base de datos · MLflow.
El frontend es cliente web y tampoco cuenta.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## 6. Trazabilidad

| Requisito | Sección | Cubierto en |
|---|---|---|
| P2-REQ-001 | §1, §3 | §2 de este documento |
| P2-REQ-002 | §3 reglas | §3 y §4 de este documento |
| P2-REQ-003 | §3 | §1 de este documento |

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer&color=D8455C" alt=""/>
</p>
