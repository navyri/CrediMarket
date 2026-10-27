# Contratos de mensajes (RabbitMQ)

Diseño de P2-1.5. Base: §5.2 (columna RabbitMQ), §5.3 y §4.

## 1. Sobre (envelope) común — obligatorio en todos los mensajes

```json
{
  "event_id": "8f2b6c1e-4a7d-4f3a-9c2e-1b5d7e9a0c3f",
  "type": "inventario.reserva.reservada",
  "schema_version": 1,
  "occurred_at": "2026-10-27T15:04:05.123Z",
  "correlation_id": "0f8a…(prestamo_id o idempotency key)",
  "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": { }
}
```

- `event_id`: UUIDv4, único por mensaje; el consumidor lo registra en `evento_procesado`
  (deduplicación durable, §5.3).
- `schema_version`: entero; incrementa ante cambio incompatible de `payload`.
- `correlation_id`: se mantiene de extremo a extremo (trazabilidad de una solicitud).
- **Los mensajes hacia Inventario NO llevan datos financieros** (ni ingresos, ni monto, ni
  `cliente_id`): solo `prestamo_id`, `producto_id`, `cantidad`, `plazo_desde` operativo (§5.3).

## 2. Topología RabbitMQ (resumen; detalle en `decision-broker.md` §7)

Exchange `credimarket.topic` (topic, durable) · colas `prestamos.comandos` e `inventario.comandos`
(durables) · dead letter `credimarket.dlx` → `prestamos.dlq`, `inventario.dlq` · publisher confirms
+ mensajes persistentes · ack después del commit.

## 3. Mensajes

### Comandos Préstamos → Inventario

#### `prestamo.reserva.solicitada` (schema_version 1)

```json
{
  "event_id": "…", "type": "prestamo.reserva.solicitada", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "prestamos",
  "payload": {
    "prestamo_id": "PRE-0000042",
    "producto_id": "PROD-1001",
    "cantidad": 1,
    "plazo_dias": 180,
    "vence_en": "2026-10-27T15:14:05Z"
  }
}
```

`vence_en` informa el tiempo de espera que Préstamos fijó (§4: documentar tiempos de espera).

#### `prestamo.reserva.cancelada` (schema_version 1)

```json
{
  "event_id": "…", "type": "prestamo.reserva.cancelada", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "prestamos",
  "payload": {"prestamo_id": "PRE-0000042", "motivo": "cancelacion_cliente"}
}
```

### Eventos Inventario → Préstamos

#### `inventario.reserva.reservada`

```json
{
  "event_id": "…", "type": "inventario.reserva.reservada", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": {"prestamo_id": "PRE-0000042", "reserva_id": "RES-0000123", "producto_id": "PROD-1001", "cantidad": 1, "vence_en": "…"}
}
```

→ Préstamos: `PENDIENTE_INVENTARIO → APROBADA` (solo tras confirmar, §4).

#### `inventario.reserva.insuficiente`

```json
{
  "event_id": "…", "type": "inventario.reserva.insuficiente", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": {"prestamo_id": "PRE-0000042", "producto_id": "PROD-1001", "solicitado": 1, "disponible": 0}
}
```

→ `PENDIENTE_INVENTARIO → CANCELADA_SIN_STOCK` (§4).

#### `inventario.reserva.liberada`

```json
{
  "event_id": "…", "type": "inventario.reserva.liberada", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": {"prestamo_id": "PRE-0000042", "reserva_id": "RES-0000123", "origen": "cancelacion"}
}
```

→ Préstamos completa la cancelación (`→ CANCELADA`).

#### `inventario.reserva.vencida`

```json
{
  "event_id": "…", "type": "inventario.reserva.vencida", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": {"prestamo_id": "PRE-0000042", "reserva_id": "RES-0000123", "origen": "vencimiento", "vencio_en": "…"}
}
```

→ Préstamos: `APROBADA → CANCELADA_VENCIDA` (estado nuevo documentado; §4 pide estado/motivo
coherente: **un préstamo aprobado no puede conservar una reserva inexistente**). Un evento tardío
**nunca** reactiva un préstamo en estado final (§4).

#### `inventario.salida.confirmada`

```json
{
  "event_id": "…", "type": "inventario.salida.confirmada", "schema_version": 1,
  "occurred_at": "…", "correlation_id": "PRE-0000042", "prestamo_id": "PRE-0000042",
  "producer": "inventario",
  "payload": {"prestamo_id": "PRE-0000042", "reserva_id": "RES-0000123", "entregado_en": "…"}
}
```

→ Préstamos: `APROBADA → COMPLETADA` (§4).

## 4. Garantías y errores (§5.2/§5.3)

- **Publicación:** outbox en el productor (P2-REQ-039); relay publica con `publisher confirm`;
  mensaje `persistent`; si no hay confirmación → reintento del relay, nunca perder el registro.
- **Consumo:** `manual ack` **después** del commit local que aplica el efecto y registra
  `evento_procesado{event_id}` (unicidad); un `event_id` repetido → ack inmediato sin repetir efecto
  (prueba #5).
- **Reintentos:** 3 intentos (contador en la cola con TTL de reintento); después → dead letter
  (`prestamos.dlq` / `inventario.dlq`), visible en la UI de RabbitMQ.
- **Carrera cancelación/confirmación:** si llega `reserva.reservada` con el préstamo ya cancelado,
  Préstamos responde publicando `prestamo.reserva.cancelada` y **no** reactiva el estado; si llega
  `salida.confirmada` sobre un préstamo cancelado, se registra como evento tardío en log con
  `correlation_id` sin cambio de estado (prueba #7).
- **Caída:** mensajes durables + ack posterior al commit + outbox cubren la caída entre guardar y
  publicar (prueba #6).

Ejemplos JSON completos versionados en `docs/contratos/ejemplos/` (se generan en P2-1.5 como parte
de este entregable, junto con los esquemas).
