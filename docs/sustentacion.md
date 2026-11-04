# Guion de sustentación CrediMarket (§14)

> Base: **§14 «Sustentación»** (demostración ejecutada **a partir de lo entregado en el
> repositorio**), **§15 (rúbrica)** y **§12 (16 casos de aceptación)**. Cada bloque de este
> guion indica el tiempo, el comando o pantalla que se ejecuta y la evidencia que se muestra.
>
> **Composición del grupo (declarada, P2-DEC-003/006):** el enunciado asume grupos de cuatro
> integrantes; este proyecto lo desarrolló **un solo integrante real (Mariana)**. No se
> inventaron autores: la evidencia de contribución es el historial real de commits de
> `main` en GitHub y los nombres se completan solo si el profesor lo solicita por canal
> privado.

---

## 1. Guion de arquitectura (≤ 5 min) — P2-12.1

Fuentes: [`docs/arquitectura/`](arquitectura/) (diagramas, contratos, máquina de estados,
decisión de broker, seguridad) y [`README.md`](../README.md).

### 1.1 · Panorama (≈ 45 s)

Cuatro microservicios con responsabilidades y datos separados, más infraestructura compartida:

| Servicio | Tecnología | Puerto | Responsabilidad | Datos |
|---|---|---|---|---|
| **Productos** | Python · FastAPI | 8001 | Catálogo, cotización vigente con versión, caché del listado | esquema `productos` |
| **Clientes** | Python · FastAPI | 8002 | Cuentas, perfiles financieros, **emisión de JWT** (roles `cliente`/`administrador`) | esquema `clientes` |
| **Préstamos** | Python · FastAPI | 8003 | Solicitud idempotente, **modelo de riesgo**, ciclo MLOps (MLflow) | esquema `prestamos` |
| **Inventario** | Python · FastAPI | 8004 | Existencias, reservas atómicas, consumidor del broker | esquema `inventario` |

Infraestructura (Compose, 9 contenedores): **PostgreSQL 17** (instancia única con **4 esquemas y
4 usuarios `svc_*` restringidos**), **RabbitMQ 4** (exchange `credimarket.topic` + DLX
`credimarket.dlx`), **Redis 8** (caché *cache-aside*), **MLflow 3.17** (experimentos y registro)
y **frontend nginx** (build de producción en el puerto **8090**).

### 1.2 · Propiedad de datos (≈ 45 s)

- Cada servicio es el **único dueño** de su esquema; los demás se conectan con un usuario
  propio que **no tiene permisos sobre esquemas ajenos** (verificado en el init de PostgreSQL:
  `01_esquemas.sh` crea roles y esquemas; un intento cruzado falla con `permission denied`).
- **No hay acceso directo a tablas de otro servicio**: todo cruce pasa por la API REST
  (contratos en [`docs/arquitectura/contratos-rest.md`](arquitectura/contratos-rest.md)) o por
  eventos de mensaje ([`contratos-mensajes.md`](arquitectura/contratos-mensajes.md), 7 ejemplos
  JSON versionados).
- La **autorización se valida en backend** (no solo en el frontend): el guardián JWT devuelve
  `401` sin token y `403` con `detail` anidado cuando el rol o el dueño del recurso no
  coinciden — caso 13 de aceptación (cliente accede a préstamos ajenos).

### 1.3 · Flujo de una solicitud (≈ 90 s)

Ejecutar el caso feliz en el navegador mientras se explica (paso 3.2 de la guía de demo):

1. **Entrada**: `POST /prestamos` con `Idempotency-Key`; el navegador **nunca** envía precio ni
   tasa (los calcula el sistema con la cotización vigente de Productos, que se **guarda con su
   versión** en el préstamo).
2. **Validación**: errores de negocio → `400` con `problem+json` y lista `errors[]`.
3. **Decisión**: reglas de control (p. ej. obligaciones ≥ ingresos → `RECHAZADA` con motivo) o
   inferencia del modelo (`probabilidad` vs `umbral` congelado). Favorable →
   **`202 PENDIENTE_INVENTARIO`** con el préstamo y el evento `prestamo.reserva.solicitada`
   escritos en **una sola transacción (outbox)**.
4. **Broker**: RabbitMQ transporta `inventario.reserva.solicitada` → Inventario reserva de
   forma atómica (sin stock negativo) → publica `reservada` o `insuficiente`.
5. **Cierre**: Préstamos transiciona a **`APROBADA`** (con `reserva_id`) o
   **`CANCELADA_SIN_STOCK`**; la entrega confirma **`COMPLETADA`**; cancelar libera la reserva
   (**`CANCELADA`**) y el vencimiento produce **`CANCELADA_VENCIDA`** (estado propio, T8).
6. **Resiliencia**: eventos tardíos **no reactivan** un estado final (T9, log
   `evento_tardio_ignorado`); la máquina de estados completa (T1–T9) está en
   [`docs/arquitectura/maquina-estados.md`](arquitectura/maquina-estados.md).

### 1.4 · Ciclo MLOps (≈ 60 s)

- El modelo **vive dentro de Préstamos** (no hay quinto servicio): `GET /ready` responde `503`
  sin modelo activo y `GET /modelo/info` expone versión, umbral y `run_id`.
- Experimento `credimarket-incumplimiento-90d` en MLflow: **baseline + 7 candidatas**
  (≥ 3 algoritmos), ≥ 6 corridas por iteración, métrica de selección **predeclarada**
  (mayor ROC-AUC en validación → menor Brier → orden de la parrilla), **umbral congelado por
  F1 = 0,49** y **costos ficticios** (aprobar malo 100 · rechazar bueno 25) con curva de costos.
- Exportación por versión (`ml/modelos/{v1,v2}/` con `modelo.joblib` + `metadatos.json` +
  `importancias.csv`), **promoción y rollback explícitos** (`ml/export/administrar_activo.py`,
  validan el artefacto antes de activarlo), **recarga en caliente** cada 10 s y **drift PSI**
  documentado (`docs/informe-seleccion-modelo.md`).
- Reproducibilidad: semilla 42, particiones estratificadas sin fuga y hash SHA-256 del CSV
  (`ml/datos/ficha_datos.json`).

### 1.5 · Decisiones registradas (≈ 60 s)

| Decisión | Resumen |
|---|---|
| P2-DEC-001 | Auth/roles/autorización en backend **obligatorios** |
| P2-DEC-002 | 2.ª versión + promoción + rollback obligatorios; monitoreo y drift en alcance |
| P2-DEC-003 | **No se inventan integrantes**; grupo real = 1 (Mariana) |
| P2-DEC-004/005 | Estructura del repo y política Git (rama `main`, add explícito, sin secretos/binarios) |
| P2-DEC-006 | Identidad pública acotada al nombre de pila |
| P2-DEC-007/008 | Estética del README y paleta (coral `D8455C` / crema `F8F2EF`) |
| P2-DEC-009 | Registros internos **no versionados**; la documentación pública sí |
| P2-DEC-010 | Stack: Python 3.14 · FastAPI · PostgreSQL 17 · Redis 8 · RabbitMQ 4 · React 19 · MLflow 3.17 |
| P2-DEC-011 | **RabbitMQ** sobre Kafka (comparación de 6 preguntas en `decision-broker.md`) |
| P2-DEC-012 | Emisión de JWT en Clientes (dueño de `usuario`), sin quinto servicio |
| P2-DEC-013 | `CANCELADA_VENCIDA` propio; estados finales **absorbentes** |

### 1.6 · Cierre (≈ 30 s)

**123 pruebas** automatizadas (unitarias + integración con infraestructura real) ·
**16/16 casos de aceptación** de §12 · **7 entregables** de §13 en el repositorio ·
arranque verificado desde un **clon limpio** (`docs/evidencias/ensayo_clon_limpio.json`).

---

## 2. Flujo en navegador: los 8 escenarios de §10 — P2-12.2

Pasos exactos en [`docs/guia-demo.md`](guia-demo.md) §3; aquí el resumen para la exposición
(ejecutar sobre `http://localhost:8090` con el Compose levantado):

| # | Escenario | Qué se hace (pantalla) | Qué se muestra |
|---|---|---|---|
| 3.2 | **Préstamo aprobado** | Catálogo → cantidad 1, plazo 12 → *Solicitar financiación* | Traza `PENDIENTE_INVENTARIO → APROBADA → COMPLETADA`, precio y **versión de cotización**, reserva en Inventario con stock descontado |
| 3.3 | **Rechazo por riesgo** | Mi perfil → obligaciones ≥ ingresos → solicitar | `RECHAZADA` con **motivo de la regla de control**, `modelo_version` guardada y **sin reserva** |
| 3.4 | **Falta de inventario** | Admin crea producto nuevo → cliente solicita | `CANCELADA_SIN_STOCK`, motivo «sin existencias suficientes», **sin stock negativo** |
| 3.5 | **Cancelación con liberación** | Mis solicitudes → solicitud aprobada → *Cancelar* | `202` → reserva `LIBERADA` y stock devuelto; entrega tardía responde `409` y **no reactiva** |
| 3.6 | **Entrega** | Admin → Inventario → Reservas → *Entregar* | `COMPLETADA` + movimiento de salida registrado |
| 3.7 | **Precio actualizado** | Admin → Catálogo → *Nuevo precio* → *Actualizar precio* | Versión del producto avanza, **clave Redis borrada** y la siguiente solicitud cotiza al precio nuevo (`scripts/medir_cache.py` → `clave_borrada: true`) |
| 3.8 | **Importación CSV** | Admin → Clientes → Archivo CSV → *Importar* (2 veces) | Resumen insertados/actualizados/sin cambios + rechazos **por fila**; la 2.ª pasada queda **sin cambios** (idempotente) |
| 3.9 | **Versión del modelo** | Admin → *Modelo* | Versión activa, `run_id`, umbral congelado, métricas, enlace a MLflow y panel de monitoreo (latencias p50/p95, deriva PSI) |

Detalle de sesión/roles: cuentas de prueba en `guia-demo.md` §2 (administrador
`admin@credimarket.demo`; cliente recién registrado en el escenario 3.1).

---

## 3. Demostración en vivo de pruebas (§12) — P2-12.3

**Comando único** (desde la raíz del clon, con el Compose levantado):

```bash
python scripts/aceptacion/ejecutar_todas.py     # 16 casos · ≈ 88 s · resultados.json
```

Salida esperada: `RESULTADO: 16/16 casos OK` y evidencia por caso en
`docs/evidencias/aceptacion/caso_XX.json` + consolidado `resultados.json`.
Si el profesor pide un caso concreto: `python scripts/aceptacion/caso_04.py` (idem 01…16).
Las **123 pruebas** de unidad/integración se ejecutan con `python scripts/ejecutar_pruebas.py`.

| Caso | Qué se verifica en vivo | Evidencia visible |
|---|---|---|
| 01 | Riesgo favorable con existencias | Reserva confirmada, préstamo aprobado y `COMPLETADA`; stock 5/0 → 3/0 |
| 02 | Solicitud rechazada | Motivo de la regla de control + `modelo_version`; `reservada=0` |
| 03 | Favorable sin existencias | `CANCELADA_SIN_STOCK`, sin inventario negativo |
| 04 | Dos solicitudes por la última unidad | Solo una obtiene la reserva (concurrencia real) |
| 05 | Misma petición y evento repetidos | **1 préstamo y 1 solo descuento**; clave repetida con cuerpo distinto → `409` |
| 06 | Caída del broker | Solicitud `202` persistida; al reiniciar RabbitMQ llega a `APROBADA` **sin duplicar** reserva |
| 07 | Cancelación y evento tardío | Estado coherente, reserva liberada, **no reactiva** |
| 08 | Redis vacío/expirado/caído | Miss → repoblado (TTL 60 s), caída → sirve desde BD, reinicio → caché activa |
| 09 | Precio modificado | Invalidación de caché y monto con el **precio nuevo** |
| 10 | Modelo exportado vs API | Predicciones **equivalentes** y versión identificable |
| 11 | Promoción y rollback | Cambio v1 → v2 → rollback con **trazabilidad** en `historial_promociones.jsonl` |
| 12 | Mismo CSV dos veces | **No se duplican** clientes |
| 13 | Préstamos ajenos | `403/401` con `detail` (autorización en backend) |
| 14 | Flujo desde el frontend | `npm ci` + build del bundle + misma secuencia que la UI |
| 15 | Solicitud pendiente y asíncrona | La interfaz muestra `PENDIENTE_INVENTARIO` y **se actualiza sola** |
| 16 | Formulario inválido / sesión vencida / API caída | Mensajes claros y estado recuperable, **sin respuestas simuladas** |

---

## 4. Respuestas: rúbrica §15.2 y limitaciones — P2-12.4

### 4.1 · Los 8 criterios y dónde está la evidencia

| # | Criterio (peso) | Nivel buscado | Dónde se demuestra |
|---|---|---|---|
| 1 | Microservicios y flujo (15 %) | Excelente | 4 servicios con datos separados (§1.2), flujo con `202`, cotización con versión guardada, máquina T1–T9 con vencimiento y eventos tardíos (`maquina-estados.md`), casos 01–07 |
| 2 | Broker (15 %) | Excelente | RabbitMQ con comandos/eventos **reales**, contratos JSON versionados (7 ejemplos), reintentos + DLX, decisión de 6 preguntas (`decision-broker.md`), casos 05–07 |
| 3 | Redis (10 %) | Excelente | Caché *cache-aside* con claves/TTL/invalidación documentados, demo de miss/hit/expiración/caída, mediciones p50/p95 + hit-rate 97,59 % (`informe-redis-desempeno.md`), precio validado contra la fuente de verdad, casos 08–09 |
| 4 | Datos y MLOps (15 %) | Excelente | EDA + hash del dataset, particiones estratificadas sin fuga, pipeline completo, baseline + 7 candidatas con ≥ 6 corridas en MLflow, métrica predeclarada, umbral justificado con costos ficticios, prueba al final (`informe-seleccion-modelo.md`), caso 10 |
| 5 | Exportación, API y versiones (15 %) | Excelente | Pipeline exportado con manifiesto, promoción/rollback explícitos, API con los 6 endpoints y validación, carga al iniciar, equivalencia demostrada (caso 10), monitoreo + drift (PSI), 2.ª versión (casos 10 y 11) |
| 6 | Seguridad, idempotencia y recuperación (15 %) | Excelente | Roles validados en backend (caso 13), idempotencia HTTP con `409` y de mensajes (caso 05), outbox demostrado (casos 05–06), reserva atómica sin stock negativo (caso 04), recuperación ante caídas (06–08), CSV idempotente (caso 12) |
| 7 | Frontend (10 %) | Excelente | Los módulos de §10 sobre APIs reales, roles y estados pendientes con actualización automática (caso 15), errores y sesión vencida manejados (caso 16), diseño adaptable, **cero respuestas simuladas** |
| 8 | Documentación y reproducibilidad (5 %) | Excelente | `git clone` → `docker compose up -d` → bootstrap documentado; README, 5 diagramas, contratos, guía de demo e informes completos; **contribución real visible en el historial de commits** (con la salvedad de grupo de 1 de §4) |

### 4.2 · Condiciones de §15.3 (cuidado especial)

- **Levantar con lo entregado:** verificado con un clon limpio de GitHub y volúmenes vacíos
  (9/9 `healthy`, modelo entrenado con los comandos del README) → `docs/evidencias/ensayo_clon_limpio.json`.
- **Nada simulado:** el broker transporta el flujo real, las aprobaciones crean reserva real en
  Inventario y el frontend llama a las APIs (no hay respuestas quemadas).
- **Sin secretos en el repo:** `.env` no está trackeado (solo `.env.example` con placeholders
  `CAMBIAR_*`), sin credenciales reales ni claves privadas (verificación en §5).

### 4.3 · Limitaciones declaradas (respuesta directa si preguntan)

1. **Datos sintéticos**: el histórico (`prestamos_entrenamiento.csv`, 12.000 filas) es
   sintético; el hash SHA-256 y el diccionario de datos están documentados (§7/§13).
2. **Umbral y costos ficticios**: el umbral servido (0,49) se eligió por F1 en validación; el
   umbral de mínimo costo (0,89) con costos ficticios 100/25 queda como análisis de
   sensibilidad, documentado en el informe.
3. **Grupo de 1 integrante** (P2-DEC-003): el enunciado asume 4; aquí no se inventaron
   autores. La evidencia de contribución es el historial real de commits.
4. **Configuración de demo**: contraseñas y JWT del `.env.example` son valores de plantilla
   para local; en cualquier despliegue real se reemplazan por secretos fuertes.
5. **Drift**: es un diagnóstico **simulado** con un lote de referencia fija
   (`solicitudes_nuevas.csv`, PSI máximo 0,1266), como permite el alcance (P2-DEC-008).

---

## 5. Cierre de entrega: verificación de integridad — P2-12.5

Ejecutar antes de la sustentación (resultados de la corrida de cierre en la bitácora):

```bash
# 1) árbol limpio y sincronizado con origin/main
git status -sb && git log --oneline -3

# 2) nada prohibido en el índice (sin .env, .joblib, CSV, node_modules, venv, .pyc)
git ls-files | findstr /R "\.env$ \.joblib$ node_modules venv \.pyc$ \.csv$"

# 3) los 7 entregables §13 en el repositorio
#    1 repositorio · 2 Compose · 3 docs/arquitectura · 4 artefactos ML (ml/ + informe)
#    5 guía de demo · 6 informe de Redis · 7 instrucciones (README §Puesta en marcha)
```

**Resultado de la corrida de cierre:**

| Verificación | Resultado |
|---|---|
| Commits en `main` sincronizados con `origin/main`, árbol limpio | ✅ |
| Archivos trackeados: 185 · `.env` no trackeado · 0 `.joblib`/`.csv`/`node_modules`/`venv`/`.pyc` | ✅ |
| Patrones de secreto (URIs con contraseña, JWT, llaves privadas) en archivos trackeados | ✅ ninguno |
| 7 entregables §13 presentes (17 archivos clave verificados) | ✅ |
| `docs/arquitectura/`: 9 documentos, 5 diagramas Mermaid, 7 ejemplos JSON de contratos | ✅ |
| 16 casos `scripts/aceptacion/caso_*.py` + `ejecutar_todas.py` | ✅ |
| Arranque desde clon limpio: 9/9 `healthy`, 123 pruebas, 16/16 aceptación, demo hasta `APROBADA` | ✅ `docs/evidencias/ensayo_clon_limpio.json` |
| Registro maestro: **191 tareas/requisitos → 191 [x], 0 pendientes** | ✅ local (no versionado, P2-DEC-009) |

**Orden sugerido de la sustentación:** §1 (arquitectura, 5 min) → §2 (flujo en navegador,
8 escenarios) → §3 (pruebas en vivo, el comando único) → §4 (preguntas de la rúbrica).
