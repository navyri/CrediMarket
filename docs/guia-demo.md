# Guía de demostración CrediMarket (entregable 5)

Todo el flujo se ejecuta **desde el navegador** contra las APIs reales: no hay respuestas
simuladas en el frontend, cada pantalla llama a los microservicios y los datos quedan
persistidos en PostgreSQL (§10).

## 1. Levantar el sistema

```bash
cp .env.example .env      # editar valores si hace falta
docker compose up -d      # 9 contenedores: 4 servicios + frontend + infraestructura
```

**Si el sistema nace de un clon limpio** (sin `ml/modelos/*.joblib` ni datos),
faltan dos pasos antes de la demo; sin ellos `GET /ready` da 503 y el catálogo
sale vacío:

```bash
python scripts/preparar_desde_clon.py --csv "ruta/al/prestamos_entrenamiento.csv"
#   → ml/datos/*.csv + entrena v1 y v2 (semilla 42) + promueve v1 + verifica /ready
python scripts/sembrar_demo.py
#   → catálogo DEMO-01…DEMO-06 con stock (DEMO-06 sin existencias, escenario 3.4)
```

Ambos son **idempotentes**: repetirlos no duplica productos ni reentrena dos
veces lo mismo (el segundo se puede omitir si `ml/modelos/v1/modelo.joblib`
ya existe).

| Componente | URL en el host |
|---|---|
| Frontend (nginx, build de producción) | **http://localhost:8090** |
| API Productos | http://localhost:8001 |
| API Clientes | http://localhost:8002 |
| API Préstamos | http://localhost:8003 |
| API Inventario | http://localhost:8004 |
| Interfaz MLflow | http://localhost:5000 |
| RabbitMQ (management) | http://localhost:15672 |
| PostgreSQL | localhost:5434 |
| Redis | localhost:6379 |

Comprobación rápida: `docker compose ps` debe mostrar los 9 servicios `healthy`.

## 2. Cuentas de prueba

| Rol | Correo | Contraseña | Cómo se obtiene |
|---|---|---|---|
| Administrador | `admin@credimarket.demo` | `CAMBIAR_admin_local` | Semilla: se crea en el arranque de Clientes |
| Cliente (demo) | el que registre en el paso 3 | el que elija (≥ 8 caracteres) | Registro público desde la propia interfaz |

Los valores por defecto viven en `.env` (`ADMIN_EMAIL`/`ADMIN_PASSWORD` y
`JWT_SECRET`); en un despliegue real se sustituyen. **No hay secretos en el código
del frontend**: las URLs salen de `VITE_API_*` en el build y el JWT solo vive en el
navegador.

> La sesión dura 30 minutos; al vencer, la interfaz muestra el aviso de sesión
> vencida y devuelve al formulario de acceso (§10, requisitos transversales).

## 3. Flujo completo paso a paso (8 escenarios obligatorios, §10)

### 3.1 Crear la cuenta de cliente y su perfil

1. Abra **http://localhost:8090** → pestaña **Crear cuenta**.
2. Nombre, documento, correo y contraseña (≥ 8) → **Registrarse**. La interfaz
   redirige a *Mi perfil* y guarda el `cliente_id`.
3. En **Mi perfil**, complete el perfil financiero: ingresos mensuales
   `4.000.000`, obligaciones mensuales `800.000`, tipo de empleo y antigüedad →
   **Guardar cambios**. Este perfil es el que Préstamos lee para decidir.

### 3.2 Préstamo aprobado (flujo obligatorio §4)

1. Cierre sesión y entre como **cliente** recién creado (o siga con la sesión abierta).
2. **Catálogo** → en una tarjeta con existencias: cantidad `1`, plazo `12` →
   **Solicitar financiación**. El navegador envía `Idempotency-Key`, **nunca** precio
   ni tasa (el precio lo manda Productos).
3. La respuesta llega en decenas de milisegundos como `202 PENDIENTE_INVENTARIO`;
   la pantalla *Solicitud…* hace **polling** y muestra la traza
   `PENDIENTE_INVENTARIO → APROBADA → COMPLETADA` con el precio y la versión de
   cotización usados.
4. Verifique en **Inventario** la reserva `RESERVADA` y el stock descontado.

### 3.3 Rechazo por riesgo

1. En **Mi perfil**, ponga obligaciones ≥ ingresos (p. ej. ingresos `1.000.000`,
   obligaciones `1.200.000`) → **Guardar cambios**.
2. Solicite financiación desde el catálogo.
3. Estado final **RECHAZADA** con motivo de la regla de control (por ejemplo
   *«obligaciones alcanzan o superan los ingresos»*), `modelo_version` registrada y
   **sin** reserva de inventario. Revise el motivo en *Mis solicitudes*.

### 3.4 Falta de inventario

1. Como **administrador**: **Catálogo** → **＋ Nuevo producto** (SKU, nombre,
   categoría, precio) → **Crear**. El producto nace sin existencias registradas.
2. Como **cliente**: solicite ese producto.
3. Estado final **CANCELADA_SIN_STOCK** con motivo
   *«sin existencias suficientes»*, sin reserva y sin stock negativo.

### 3.5 Cancelación (con liberación de reserva)

1. Con una solicitud **APROBADA** (paso 3.2), abra **Mis solicitudes** → la
   solicitud → botón **Cancelar**.
2. El backend responde `202` y libera la reserva de forma asincrónica; la interfaz
   actualiza el estado y, en **Inventario**, la reserva pasa a `LIBERADA` con el
   stock devuelto. Una entrega tardía sobre esa reserva responde `409` y **no**
   reactiva el préstamo.

### 3.6 Entrega

1. Como **administrador** → **Inventario** → **Reservas** → **Entregar**.
2. Inventario confirma la salida y Préstamos registra **COMPLETADA**; la pantalla
   del préstamo lo refleja en la siguiente consulta y los **Movimientos** muestran
   la salida.

### 3.7 Actualización de un precio (y su invalidación en Redis)

1. Como **administrador** → **Catálogo** → en la tarjeta: *Nuevo precio (COP)* →
   **Actualizar precio**.
2. La versión del producto avanza, la entrada de Redis `productos:v1:{id}` se
   borra y la siguiente solicitud cotiza al precio nuevo (no al viejo).
   Verificación desde la terminal:
   `python scripts/medir_cache.py` → `clave_borrada: true`.

### 3.8 Importación de clientes (CSV)

1. Como **administrador** → **Clientes** → **Archivo CSV** (encabezados del
   histórico `prestamos_entrenamiento.csv`) → **Importar**.
2. La interfaz muestra el resumen: insertados / actualizados / sin cambios y el
   motivo de rechazo **por fila** (p. ej. documento repetido). Repita la
   importación: la segunda vez todo queda *sin cambios* (idempotente).

### 3.9 Versión del modelo utilizada

1. Como **administrador** → **Modelo**.
2. Se muestran versión activa (`model_version`), `run_id`, umbral congelado,
   métricas, enlace a MLflow y el panel de monitoreo (latencias p50/p95, tasa
   sobre umbral y deriva PSI). Cada préstamo guarda en su registro la versión con
   la que se decidió.

## 4. Demo complementaria con scripts (fallos, concurrencia, caché, reentrega)

Estos escenarios no se fuerzan desde la interfaz; se ejecutan con scripts y su
resultado final **sí se observa en el navegador** (§10):

```bash
python scripts/aceptacion/ejecutar_todas.py     # 16 casos de §12 → 16/16 OK (~81 s)
python scripts/ejecutar_pruebas.py              # 122 pruebas pytest (unitarias + integración)
python scripts/medir_cache.py                   # MISS/HIT/invalidación con métricas
```

Cobertura de los 16 casos: aprobado, rechazo, sin stock, concurrencia por la última
unidad, idempotencia de petición y de evento, caída de RabbitMQ con outbox,
cancelación con evento tardío, Redis vacío/expirado/caído, precio modificado,
equivalencia joblib vs API, promoción/rollback, importación CSV, autorización 403,
flujo del frontend, traza de polling y validaciones con sesión vencida.

## 5. Evidencias

- `docs/evidencias/aceptacion/caso_01.json` … `caso_16.json` + `resultados.json`
  (16/16 OK) — se regeneran con `scripts/aceptacion/ejecutar_todas.py`.
- `docs/evidencias/mediciones_cache.json` — MISS/HIT/invalidación de Redis.
- `docs/evidencias/p2_test_019_redis_cache.json` y
  `docs/evidencias/p2_test_020_drift_simulado.json` — métricas de caché y deriva.
- Historial de MLflow en http://localhost:5000 (volumen `mlflowdata`).
