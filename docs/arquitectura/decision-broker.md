# P2-DEC-011 · Decisión de broker: RabbitMQ

Documento de P2-1.3 (§5.1 del enunciado: 1 a 2 páginas respondiendo las seis preguntas).

## 1. Volumen, consumidores y patrón

CrediMarket genera pocas solicitudes por minuto (demo + pruebas de aceptación: decenas de mensajes
por corrida, no miles por segundo). Hay **dos servicios** como extremos: Préstamos (productor de
comandos de reserva/cancelación, consumidor de eventos de inventario) e Inventario (productor de
eventos, consumidor de comandos), con **un grupo de consumidores por cola** y patrón
comando/evento dirigido (no fan-out, no streaming de datos).

## 2. Conservación y reproducción de eventos

Se necesita conservar mensajes durante la vida de la demo y poder reproducir el flujo tras una caída
(heladera/reinicio de contenedores). RabbitMQ ofrece colas durables y mensajes persistentes que
sobreviven al reinicio del broker con almacenamiento en disco; para CrediMarket eso es suficiente.
Kafka ofrecería retención temporal y re-play por offset, pero no necesitamos reproducir un historial
de semanas ni re-analizar eventos históricos: el requisito §5 es transportar el flujo real con
recuperación, no construir un log de eventos duradero a largo plazo.

## 3. Distribución del trabajo y orden

El orden por `prestamo_id` (una reserva, su liberación y su entrega deben verse en orden) se consigue
enviando esos mensajes con la **misma routing key lógica hacia la misma cola** y un único consumidor
por cola durante la demo; en RabbitMQ el orden dentro de una cola está garantizado. En Kafka habría
que fijar particiones por clave `prestamo_id` y discutir rebalanceos; aquí el volumen no lo justifica.

## 4. Errores, duplicados, reintentos y mensajes fallidos

- Reintentos limitados: contador en la cola (retry con TTL) hasta 3 intentos.
- Mensajes fallidos: **dead letter** explícita (`credimarket.dlx` → cola `*.dlq`) con routing keys
  para diagnosticar el motivo.
- Duplicados: el broker **no** garantiza exactamente-una-vez (§5.3); la deduplicación es durable en
  la base del consumidor (`evento_procesado` + efecto en la misma transacción) y el ack se emite
  después del commit (P2-REQ-038).
- Publicación: **publisher confirms** + mensajes persistentes (§5.2 RabbitMQ), con outbox en el
  productor (P2-REQ-039).

## 5. Costo de recursos y complejidad operativa

RabbitMQ: una imagen (~200 MB) con panel de administración incluido (`:management`), sin ZK/KRaft, arranque en
segundos, memoria muy por debajo de Kafka en este volumen. Kafka con KRaft requiere más memoria y
más configuración (topics, retenciones, offsets, grupos) que solo se amortiza con alto volumen o
retención analítica. En un portátil con Docker Desktop, RabbitMQ es la opción más liviana.

## 6. Por qué elegimos RabbitMQ y qué cambio nos haría escoger Kafka

Elegimos RabbitMQ por: volumen bajo, necesidad de comandos con acuse (confirm/ack) y DLX claras,
panel de inspección para la demo, y menor costo operativo. **Cambiaríamos a Kafka** si: hubiera
varios consumidores independientes del mismo flujo, se exigiera retención temporal con replay
(histórico auditable), el orden por clave con múltiples particiones y rebalanceos fuera un requisito,
o el volumen creciera a cientos de mensajes por segundo con consumidores escalados.

## 7. Configuración a documentar (§5.2 columna RabbitMQ)

| Elemento | Valor |
|---|---|
| Exchange | `credimarket.topic` (topic, durable) |
| Routing keys | `prestamo.reserva.solicitada`, `prestamo.reserva.cancelada`, `inventario.reserva.reservada`, `inventario.reserva.insuficiente`, `inventario.reserva.liberada`, `inventario.reserva.vencida`, `inventario.salida.confirmada` |
| Colas | `prestamos.comandos` (bind `inventario.#`), `inventario.comandos` (bind `prestamo.#`), `*.dlq` vía `credimarket.dlx` |
| Persistencia | mensajes persistentes + colas durable; confirms de publicación activados en cada canal emisor |
| Acknowledgements | ack manual **después** del commit local del efecto |
| Reintentos | 3 intentos con TTL de reintento; luego dead letter |
| Inspección | UI en puerto 15672 para la demostración |

Referencia oficial: https://www.rabbitmq.com/docs/reliability (§16 del enunciado).
