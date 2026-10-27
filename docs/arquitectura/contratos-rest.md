# Contratos REST y manejo de errores

Diseño de P2-1.4. Base: §4, §8.E, §9, §10 del enunciado. Cada servicio publica OpenAPI
(`/docs`) que se genera desde FastAPI; este documento fija las rutas y semánticas.

## Convenciones comunes (los 4 servicios)

- JSON UTF-8; nombres en `snake_case`; fechas ISO-8601 UTC.
- Autenticación: `Authorization: Bearer <JWT>` (P2-1.8). Endpoints marcados `(público)` no lo exigen.
- Errores, con `Content-Type: application/problem+json` (RFC 9457):

```json
{
  "type": "about:blank",
  "title": "Recurso no encontrado",
  "status": 404,
  "detail": "producto 9f3c… no existe",
  "instance": "/productos/9f3c…",
  "errors": [{"campo": "cantidad", "mensaje": "debe ser >= 1"}]
}
```

| status | Uso |
|---|---|
| 400 | validación de entrada (`errors` detalla campos) |
| 401 | token ausente o inválido / sesión vencida |
| 403 | rol insuficiente o recurso de otro cliente (§12.13) |
| 404 | recurso inexistente |
| 409 | Idempotency-Key repetida con contenido distinto; transición inválida |
| 422 | cuerpo bien formado pero tipos/rangos inválidos (FastAPI) |
| 503 | dependencia crítica no disponible (`/ready` lo refleja) |

## Servicio Productos (puerto 8001)

| Método y ruta | Rol | Semántica |
|---|---|---|
| `GET /productos` | público | listado paginado con `categoria`, `solo_activos=true` por defecto |
| `GET /productos/{id}` | público | detalle; **cache-aside Redis** (§6): hit → Redis, miss → BD + TTL |
| `POST /productos` | administrador | crea; devuelve `producto_id`, `version=1` |
| `PATCH /productos/{id}` | administrador | actualiza precio/categoría/nombre; **incrementa `version`** y tras commit invalida la clave Redis |
| `POST /productos/{id}/desactivar` | administrador | `activo=false`; incrementa `version`; invalida caché |
| `GET /productos/{id}/cotizacion` | interno (token de servicio) | **fuente de verdad**: lee BD (no Redis) y devuelve `{producto_id, precio_cop, version, vigente_desde}`. Préstamos persiste `precio` + `version` (§4) |
| `GET /health` (público) / `GET /ready` (público) | — | procesa / BD+Redis listos |

Reglas: el precio del préstamo **nunca** sale de una caché sin validar versión (§6). El cliente no
envía precio en la solicitud de préstamo (§4).

## Servicio Clientes (puerto 8002)

| Método y ruta | Rol | Semántica |
|---|---|---|
| `POST /clientes` | público (registro) o administrador | crea cliente; clave externa única: `documento_identidad` (P2-SUP-006) |
| `GET /clientes` | administrador | listado |
| `GET /clientes/{id}` | dueño o administrador | 403 si es ajeno y no es admin |
| `PATCH /clientes/{id}` | dueño o administrador | actualización parcial |
| `POST /clientes/import` | administrador | multipart `file`; respuesta `{procesadas, insertados, actualizados, rechazadas, errores:[{fila, motivo}]}` (§9) |
| `POST /auth/token` | público | login → JWT (P2-1.8: la demo emite tokens de prueba de forma controlada, §9) |
| `GET /health` / `GET /ready` | público | lo básico |

Política de importación (se fija aquí, P2-REQ-040): clave `documento_identidad`; fila ya existente y
con datos distintos → **actualiza** y cuenta en `actualizados`; fila inválida → `rechazadas` con
motivo por fila; repetir el mismo archivo → 0 insertados, 0 actualizados (idempotente, §12.12).

## Servicio Préstamos (puerto 8003)

| Método y ruta | Rol | Semántica |
|---|---|---|
| `POST /prestamos` | cliente autenticado | **Requiere cabecera `Idempotency-Key`**. Cuerpo: `{cliente_id, producto_id, cantidad, plazo_meses}`. Sin precio (§4). Respuesta favorable: **HTTP 202** `{prestamo_id, estado:"PENDIENTE_INVENTARIO", ...}`; desfavorable: 201 con `estado:"RECHAZADA"` y `motivo`; misma clave + mismo cuerpo → misma respuesta; misma clave + cuerpo distinto → **409** (§9) |
| `GET /prestamos/{id}` | dueño o administrador | estado, decisión, motivo, `modelo_version`, `umbral`, precio y versión usados; 403 si es ajeno (§12.13) |
| `GET /prestamos` | cliente: propios · administrador: todos | listado paginado |
| `POST /prestamos/{id}/cancelar` | dueño o administrador | solo desde `PENDIENTE_INVENTARIO` o `APROBADA`; libera reserva vía broker y termina en `CANCELADA` (§4) |
| `POST /riesgo/predict` | interno/administrador | inferencia aislada; **no** reserva inventario (§8.E) |
| `GET /modelo/info` | administrador | `{modelo_version, run_id, umbral, variables[], fecha_promocion, mlflow_url}` (§8.E) |
| `POST /admin/modelo/promover` | administrador | promoción explícita de candidato → activa; `{"modelo_version":…}` (§8.D) |
| `GET /health` / `GET /ready` | público | `/ready` = 503 si el modelo no cargó (§8.E) |

Nota: la cancelación con reserva confirmada publica `prestamo.reserva.cancelada` y espera
`inventario.reserva.liberada` antes de terminar `CANCELADA` (§4: la cancelación final requiere
resolver la reserva).

## Servicio Inventario (puerto 8004)

| Método y ruta | Rol | Semántica |
|---|---|---|
| `GET /existencias` / `GET /existencias/{producto_id}` | administrador | existencia total, reservada y disponible |
| `POST /entradas` | administrador | entrada de stock; registra `movimiento` |
| `GET /reservas` | administrador | reservas con estado y vencimiento |
| `GET /movimientos` | administrador | historial |
| `POST /reservas/{id}/entrega` | administrador | confirma salida (entrega simulada §4); publica `inventario.salida.confirmada` |
| `POST /reservas/{id}/liberar` | administrador | liberación manual; publica `inventario.reserva.liberada` |
| `GET /health` / `GET /ready` | público | lo básico |

Las reservas **no** se crean por REST: llegan por broker (`prestamo.reserva.solicitada`) y se aplican
con transacción atómica `UPDATE ... WHERE disponible >= cantidad` (P2-REQ, §4; prueba #4/#3).

## Frontend → servicios

El navegador solo llama a estas APIs con JWT (§10); no toca BD, Redis, broker ni MLflow. Las URLs de
cada servicio se configuran por variables de entorno del build (`VITE_API_*`).
