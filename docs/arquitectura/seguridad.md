# Seguridad, roles e idempotencia

Diseño de P2-1.8. Base: §9 (tabla), §10 (acceso y roles), §4 (cliente autenticado), §15.2 c6.
Interpretación aplicada: P2-DEC-001 (autenticación y roles **obligatorios** pese a las etiquetas
"Opcional" de §9/§10).

## 1. Identidad y emisión de tokens

- **Sin quinto servicio:** la autenticación vive en **Clientes** (dueño de `usuario`), que es un
  servicio de negocio existente. §9 permite "emitir tokens de prueba de forma controlada".
- `POST /auth/token` (Clientes): `{email, password}` → JWT firmado (HS256) con
  `{sub: usuario_id, cliente_id, rol, exp}`. `exp` = 30 min (demo).
- `POST /auth/registro` (Clientes): crea `usuario` con hash bcrypt (bcrypt 5.0.0 instalado) y su
  `cliente` vinculado.
- Semilla de demo: 1 administrador y 2 clientes (cuentas documentadas en la guía de demo, P2-11.5;
  contraseñas en archivo `.env` **fuera del repo**, nunca en el código — §9 y §15.3).

## 2. Roles

| Rol | Alcance |
|---|---|
| `cliente` | solo sus propios préstamos (GET/POST/DELETE propios); sus datos de cliente; catálogo público |
| `administrador` | productos (CRUD), clientes e importación, inventario, `modelo/info`, promoción, todos los préstamos |
| `servicio` (interno) | token de servicio para Préstamos → Clientes/Productos (cotización, datos). Firmado con el mismo secreto, con `rol=servicio`; **no se emite a usuarios** |

## 3. Protección interna (§9: "no basta con confiar en un cliente_id recibido")

- Toda llamada servidor→servidor envía `Authorization: Bearer <token de servicio>`. Productos y
  Clientes validan firma, `exp` y rol (`servicio` o `administrador`) en el endpoint interno de
  cotización/consulta.
- El `cliente_id` del cuerpo de `POST /prestamos` se **valida contra el token del usuario** (el
  cliente solo puede solicitar a su propio `cliente_id`; 403 si difiere) y, además, Préstamos confirma
  con la API de Clientes que el cliente existe y está activo (reglas de negocio §4).
- La autorización se hace en **cada backend**, nunca solo en el frontend (§10, rúbrica c6/c7).
- Los endpoints internos (cotización, `/riesgo/predict`, promoción) rechazan tokens de rol `cliente`
  con 403.

## 4. Protección de endpoints administrativos

Todas las rutas marcadas administrador en `contratos-rest.md` exigen `rol=administrador`. Cualquier
acceso de un `cliente` a préstamo ajeno ⇒ 403 (prueba #13); a endpoints admin ⇒ 403.

## 5. Secretos

- El secreto JWT, credenciales de BD y de servicios viven en `.env` (gitignored; `.env.example` sin
  valores reales). Nunca en el código ni en el frontend (`VITE_*` solo expone URLs públicas).
- §15.3: secretos en el repo limitan el criterio 6 a "En desarrollo" → revisión final P2-11.9.

## 6. Idempotencia HTTP (§9, P2-REQ-037)

- `POST /prestamos` **exige** `Idempotency-Key` (400 sin ella).
- Tabla `prestamos.idempotency_key(key, cliente_id, request_hash, prestamo_id, response_status,
  response_body, created_at)` con **única por `key`**.
  - Misma key + mismo `request_hash` → se devuelve la respuesta almacenada (mismo `prestamo_id`,
    mismo status; replay idéntico).
  - Misma key + distinto `request_hash` → **409** con `problem+json`.
  - Carrera: la restricción UNIQUE hace que dos peticiones concurrentes con la misma key solo
    puedan insertar una; la segunda recibe 409/respuesta ya existente (dependencia durable en BD,
    no en memoria ni Redis — §6 y §9).
- La fila de la key, el préstamo y el registro outbox se crean en **una transacción**.

## 7. Idempotencia de mensajes y outbox (§9)

- `eventos_procesados(event_id PK, prestamo_id, procesado_en)` + efecto de negocio en la misma
  transacción local; `ack` al broker **después** del commit (P2-REQ-038).
- `outbox(id, routing_key, mensaje_json, creado_en, publicado_en NULL)` escrito en la misma
  transacción del efecto; un relay (proceso en el propio servicio, **no** un quinto servicio)
  publica con `publisher confirm` y marca `publicado_en`. Cubre la caída entre guardar y publicar
  (P2-REQ-039, pruebas #5/#6).
- Deduplicación **durable en BD**, jamás en Redis (§6).

## 8. Frontend

- Guarda el JWT en memoria + `sessionStorage` (cierre de pestaña ⇒ sesión vencida manejada, §10);
  interceptor que redirige a login en 401; mensajes claros de error; sin secretos en el bundle;
  CORS restringido por variable de entorno en cada servicio.
