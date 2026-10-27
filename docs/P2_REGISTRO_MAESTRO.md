# Registro Maestro P2 — CrediMarket

> Etapa P2-0 · Inicializado: 2026-10-27 · Estado: [x] Etapa P2-0 completada (P2-0.1–0.7 [x]) · Grupo real: 1 integrante (Mariana)

## 1. Fuentes (nombres reales verificados)

| Archivo | Ruta real verificada | Bytes | SHA-256 (verificado) |
|---|---|---|---|
| Enunciado_CrediMarket.docx | `C:\Users\maria\Downloads\final parte 2\Enunciado_CrediMarket.docx` | 46.131 | (texto extraído a `_enunciado_texto.txt`, P2-ART-001) |
| prestamos_entrenamiento.csv | `C:\Users\maria\Downloads\final parte 2\prestamos_entrenamiento.csv` | 1.318.282 | `c6cdc437c3aecc9116bc8b978df421d5a7600634c1ad7d6f82e58222a2446ecd` |
| solicitudes_nuevas.csv | `C:\Users\maria\Downloads\final parte 2\solicitudes_nuevas.csv` | 21.840 | `1430d7b34e924d5e4170c4fb9d9a412c1000af17c062af513ef15e44a1a7f1f7` |

Sin sufijos en los nombres. Ninguna ruta asumida: verificadas con `Get-ChildItem` y hashing propio.

## 2. Entorno verificado (P2-0.5)

| Componente | Versión / estado observado |
|---|---|
| SO | Windows 11 (win32), PowerShell 5.1.26100.9711 |
| Python | 3.14.2 (`C:\Python314\python.exe`); **sin pandas** instalado (inspección CSV hecha con librería estándar `csv`) |
| Git | 2.52.0.windows.1 |
| Docker | Cliente 29.7.2 + Compose v5.4.0; **daemon NO corriendo** (Docker Desktop instalado, apagado) |
| Node/npm | v24.13.0 / 11.6.2 |
| Directorio de trabajo | `C:\Users\maria\Downloads\CrediMarket` — **vacío (0 archivos), NO es repositorio Git** |

## 3. Checklist P2 (137 tareas)

Leyenda: [ ] Pendiente · [~] En progreso/aprobación · [x] Hecho y verificado · [!] Bloqueado

### ETAPA P2-0 — Lectura y entorno
- [x] P2-0.1 Leer el DOCX completo. (303 líneas/16 secciones + rúbrica extraídas; ver P2-ART-002)
- [x] P2-0.2 Localizar e inspeccionar ambos CSV. (ver §4)
- [x] P2-0.3 Extraer requisitos, entregables, aceptación y rúbrica. (ver §5)
- [x] P2-0.4 Registrar contradicciones y acordar interpretación. (CON-001..005 en §6; interpretaciones adoptadas como P2-DEC-001..003, sin eliminar requisitos)
- [x] P2-0.5 Verificar repositorio, SO, shell, herramientas y recursos. (ver §2; nota: daemon Docker apagado → SUP-003)
- [x] P2-0.6 Registrar integrantes reales y responsabilidades. (grupo real: **1 integrante — Mariana**; identidad pública acotada a nombre de pila por P2-DEC-006)
- [x] P2-0.7 Aprobar plan, estructura y política de Git. (adoptados como P2-DEC-004 y P2-DEC-005)

### ETAPA P2-1 — Diseño y contratos
- [ ] P2-1.1 … P2-1.10 (10 tareas) — no iniciadas.

### ETAPA P2-2 — Base reproducible
- [ ] P2-2.1 … P2-2.8 (8 tareas) — no iniciadas. *Nota: requiere daemon Docker activo (P2-0.5).*

### ETAPA P2-3 — Productos, Clientes y seguridad
- [ ] P2-3.1 … P2-3.10 (10 tareas) — no iniciadas.

### ETAPA P2-4 — Inventario y mensajería confiable
- [ ] P2-4.1 … P2-4.11 (11 tareas) — no iniciadas.

### ETAPA P2-5 — Datos y preparación MLOps
- [ ] P2-5.1 … P2-5.9 (9 tareas) — no iniciadas.

### ETAPA P2-6 — Entrenamiento y MLflow
- [ ] P2-6.1 … P2-6.11 (11 tareas) — no iniciadas.

### ETAPA P2-7 — Exportación y servicio de Préstamos
- [ ] P2-7.1 … P2-7.17 (17 tareas) — no iniciadas.

### ETAPA P2-8 — Frontend real
- [ ] P2-8.1 … P2-8.12 (12 tareas) — no iniciadas.

### ETAPA P2-9 — Versiones, monitoreo y desempeño
- [ ] P2-9.1 … P2-9.9 (9 tareas) — no iniciadas.

### ETAPA P2-10 — Aceptación
- [ ] P2-10.1 … P2-10.16 (16 tareas) — no iniciadas.

### ETAPA P2-11 — Entrega reproducible
- [ ] P2-11.1 … P2-11.12 (12 tareas) — no iniciadas.

### ETAPA P2-12 — Sustentación
- [ ] P2-12.1 … P2-12.5 (5 tareas) — no iniciadas.

**Conteo total: 137 → [x]=7 · [~]=0 · [!]=0 · [ ]=130**

## 4. Datos verificados (P2-0.2) — calculado, no declarado

### prestamos_entrenamiento.csv
- 12.000 filas × 15 columnas (coincide con §7). Filas con longitudes uniformes {15}.
- Columnas: `solicitud_id, cliente_id, ingresos_mensuales_cop, obligaciones_mensuales_cop, tipo_empleo, antiguedad_laboral_meses, meses_historial_crediticio, creditos_previos, atrasos_previos_30d, porcentaje_pago_puntual, monto_solicitado_cop, plazo_meses, tasa_mensual_simulada, cuota_estimada_cop, incumplimiento_90d`.
- Etiqueta `incumplimiento_90d`: **0 → 8.333 (69,44 %) · 1 → 3.667 (30,56 %)**.
- `solicitud_id` únicos: 12.000 · `cliente_id` únicos: 12.000 (cada cliente aparece una sola vez → §8.A satisfecho en los datos originales).
- Duplicados de fila completa: **0**.
- Faltantes: `porcentaje_pago_puntual` 2.473 · `tipo_empleo` 93 · `meses_historial_crediticio` 97 · `antiguedad_laboral_meses` 91 · resto 0.
- Rangos (calculados): ingresos 1.400.000–28.000.000 COP; monto 500.000–15.000.000 COP; plazos {6,12,18,24,36}; `tasa_mensual_simulada` **constante 0.0180** (único valor → candidata a exclusión justificada, §7); `porcentaje_pago_puntual` 12,68–99,97; antigüedad 0–240 meses; historial 0–300 meses; atrasos 0–12; créditos previos 0–19.
- `tipo_empleo`: dependiente 6.765 · independiente 3.461 · temporal 1.681 · vacío 93.

### solicitudes_nuevas.csv
- 200 filas × 14 columnas (coincide con §7): mismas columnas **sin** `incumplimiento_90d`.
- IDs continuos posteriores (SOL-0012001+); **0 solapamiento** de `solicitud_id` y `cliente_id` con el histórico.
- Faltantes: `porcentaje_pago_puntual` 43 · `tipo_empleo` 2 · `antiguedad_laboral_meses` 1 · `meses_historial_crediticio` 1.
- Uso: solo inferencia (§7). Sin etiquetas → prohibido calcular métricas de clasificación con él.

## 5. Requisitos extraídos (P2-0.3) — matriz de trazabilidad inicial

| ID | Sección DOCX | Requisito (resumen) | Componente previsto | Estado |
|---|---|---|---|---|
| P2-REQ-001 | §1, §3 | Exactamente 4 microservicios (Productos, Clientes, Préstamos, Inventario) con responsabilidades y datos separados | global | [ ] |
| P2-REQ-002 | §3 reglas | Dueño de datos por servicio; prohibido consultar tablas ajenas; solo API/mensajes | global | [ ] |
| P2-REQ-003 | §3 | Préstamos en Python (FastAPI/Flask); el modelo vive en Préstamos; sin 5.º servicio ni servicio de inferencia | Préstamos | [ ] |
| P2-REQ-004 | §4 | `POST /prestamos` con `Idempotency-Key`; restricción durable; conflicto 409 | Préstamos | [ ] |
| P2-REQ-005 | §4 | Cotización vigente por API (no decide el cliente); conservar precio y versión | Préstamos←Productos | [ ] |
| P2-REQ-006 | §4 | Evaluación con pipeline exportado (mismas características que entrenamiento) | Préstamos/ML | [ ] |
| P2-REQ-007 | §4 | Decisión desfavorable → RECHAZADA y **sin** solicitar inventario | Préstamos | [ ] |
| P2-REQ-008 | §4 | Favorable → PENDIENTE_INVENTARIO + publicar `ReservaSolicitada` + HTTP 202 | Préstamos | [ ] |
| P2-REQ-009 | §4 | APROBADA solo tras reserva confirmada; sin unidades → CANCELADA_SIN_STOCK | Préstamos/Inventario | [ ] |
| P2-REQ-010 | §4 | Entrega simulada autorizada → COMPLETADA; cancelación previa libera reserva → CANCELADA | Inventario/Préstamos | [ ] |
| P2-REQ-011 | §4 | Máquina de estados completa documentada + tiempos de espera | docs | [ ] |
| P2-REQ-012 | §4 | Evento tardío **nunca** reactiva una solicitud cancelada | Préstamos | [ ] |
| P2-REQ-013 | §4 | Vencimiento de reserva con evento + cambio de estado coherente; sin aprobado con reserva inexistente | Inventario/Préstamos | [ ] |
| P2-REQ-014 | §5 | Kafka **o** RabbitMQ transportando comandos/eventos reales del flujo | infra + Préstamos/Inventario | [ ] |
| P2-REQ-015 | §5.1 | Decisión de broker (1–2 pp.) respondiendo las 6 preguntas | docs | [ ] |
| P2-REQ-016 | §5.2 | Configuración documentada según broker elegido (topics/claves/grupos/retención/offsets o exchanges/colas/routing/confirms/acks) | docs | [ ] |
| P2-REQ-017 | §5.3 | Mensajes con `event_id/message_id, type, schema_version, occurred_at, correlation_id, prestamo_id, payload` | contratos | [ ] |
| P2-REQ-018 | §5.3 | Sin información financiera innecesaria a Inventario; efectos de negocio idempotentes | contratos | [ ] |
| P2-REQ-019 | §5.2 | Reintentos limitados + dead letter en ambos brokers | broker | [ ] |
| P2-REQ-020 | §6 | Redis cache-aside real en Productos: miss → DB+TTL; escritura confirmada → invalidación; fallback con espera acotada | Productos | [ ] |
| P2-REQ-021 | §6 | Documentar claves (p. ej. `productos:v1:{id}`), TTL, invalidación y condiciones de desactualización | docs | [ ] |
| P2-REQ-022 | §6 | Cotización del préstamo desde fuente de verdad o validada por versión (no caché ciega) | Productos/Préstamos | [ ] |
| P2-REQ-023 | §6 | Evidencia: cache miss, hit, expiración, invalidación tras cambio de precio, caída de Redis | pruebas | [ ] |
| P2-REQ-024 | §6 | Deduplicación durable en base de datos, no en Redis | Préstamos/Inventario | [ ] |
| P2-REQ-025 | §7 | Objetivo `incumplimiento_90d` (clase positiva 1); datos verificados (§4) | MLOps | [x] verificación de datos |
| P2-REQ-026 | §7 | IDs y etiqueta no son características; justificar exclusión de `tasa_mensual_simulada` (constante) | MLOps | [ ] |
| P2-REQ-027 | §7 | Diccionario de datos (unidades, categorías, faltantes) — ver P2-SUP-001 | docs | [ ] |
| P2-REQ-028 | §8.A | EDA + hash SHA-256 + versionado; particiones 60/20/20 estratificadas con semilla fija conservando IDs | MLOps | [ ] |
| P2-REQ-029 | §8.A | Imputadores/codificadores/escaladores ajustados solo con entrenamiento (parte del pipeline); validación→selección, prueba→final | MLOps | [ ] |
| P2-REQ-030 | §8.B | Baseline trivial + ≥3 algoritmos + ≥6 corridas candidatas adicionales | MLOps | [ ] |
| P2-REQ-031 | §8.B | Métricas: precision, recall, F1 (clase 1), ROC-AUC, AP, matriz de confusión; calibración (Brier/curva) | MLOps | [ ] |
| P2-REQ-032 | §8.B | Métrica de selección y desempate predefinidos; umbral con costos ficticios ajustado en validación y congelado antes de prueba | MLOps | [ ] |
| P2-REQ-033 | §8.C | MLflow Tracking con metadatos y artefactos persistentes (modelo, datos/código, entorno, métricas, artefactos) | MLOps | [ ] |
| P2-REQ-034 | §8.D | Pipeline exportado (preprocesamiento+estimador) + manifiesto + promoción explícita a versión activa | MLOps | [ ] |
| P2-REQ-035 | §8.E | Endpoints: `POST /prestamos`, `GET /prestamos/{id}`, `POST /riesgo/predict`, `GET /modelo/info`, `GET /health`, `GET /ready` | Préstamos | [ ] |
| P2-REQ-036 | §8.E | Carga del pipeline al iniciar; validación de entradas con errores claros; respuesta con probabilidad, decisión de riesgo, umbral y versión | Préstamos | [ ] |
| P2-REQ-037 | §9 | Idempotencia HTTP: misma clave+contenido → misma solicitud; distinto → 409; durable en BD | Préstamos | [ ] |
| P2-REQ-038 | §9 | Idempotencia de mensajes: efecto + identificador en la misma transacción local; ack/offset después del commit | Inventario/Préstamos | [ ] |
| P2-REQ-039 | §9 | Transactional outbox (o equivalente demostrado) entre guardar y publicar | servicios | [ ] |
| P2-REQ-040 | §9 | Importación CSV de clientes idempotente: resumen insertados/actualizados/rechazados + errores por fila; clave externa única | Clientes | [ ] |
| P2-REQ-041 | §9, §11 | Secretos fuera del repo; endpoints admin restringidos; autorización también en backend | seguridad | [ ] |
| P2-REQ-042 | §10 | Frontend con módulos: acceso/roles, catálogo, clientes+importación, solicitud+idempotencia, seguimiento con polling, inventario admin, modelo admin | frontend | [ ] |
| P2-REQ-043 | §10 | Sin respuestas simuladas; el navegador solo habla con APIs; CORS configurable; carga/errores/sesión vencida/móvil | frontend | [ ] |
| P2-REQ-044 | §11, §13.2 | Docker Compose reproducible con volúmenes persistentes para datos durables | infra | [ ] |
| P2-REQ-045 | §12 | 16 pruebas de aceptación con evidencia demostrable | pruebas | [ ] |
| P2-REQ-046 | §13 | 7 entregables (repo, compose, docs de arquitectura, artefactos ML, guía de demo, informe Redis, reproducción) | entrega | [ ] |
| P2-REQ-047 | §15 | 8 criterios de rúbrica (15/15/10/15/15/15/10/5 %) como definición de "hecho" | entrega | [ ] |
| P2-REQ-048 | §15.2 c5, §12.11 | Segunda versión identificable + promoción + rollback; monitoreo y drift simulado para nivel Excelente (P2-DEC-002) | MLOps/Préstamos | [ ] |
| P2-REQ-049 | §15.2 c6 | Roles y autorización validados en backend; sin autenticación = Insuficiente en criterio 6 (P2-DEC-001) | seguridad | [ ] |
| P2-REQ-050 | §2 | README con integrantes y responsabilidades reales; contribuciones visibles en Git (grupo real: 1 integrante, ver CON-003) | entrega | [x] registrado; commits reales en curso |

## 6. Contradicciones del enunciado (P2-0.4) — interpretadas y adoptadas

> **Nota P2-0.4 (2026-10-27):** el responsable de desarrollo indicó que no requiere aprobación previa de estas interpretaciones. Se adoptan como **decisiones conservadoras registradas** (P2-DEC-001..003), orientadas a cumplir la rúbrica, sin eliminar ningún requisito. Si el profesor aclara algo distinto, se reabren.

### CON-001 · Autenticación y roles: "Opcional" vs. exigido
- **Citado:** §9 tabla, fila 1: *"Autenticación y autorización (Opcional)"* · §10 tabla: *"Acceso y roles (Opcional)"* · **pero** §4: *"Un cliente autenticado solicita…"*; §11 obligatorios: *"Frontend integrado con roles"*; §15.2 criterio 6 (Insuficiente): *"Sin autenticación…"*; criterio 7 Excelente exige roles validados en backend; §12.13: *"Cliente accede a préstamos ajenos → rechazado por autorización"*.
- **Impacto:** 25 % de la nota (criterios 6+7) dependen de que exista; el flujo §4 la presupone.
- **Interpretación conservadora adoptada (P2-DEC-001):** autenticación y roles se tratan como **obligatorios** (la rúbrica y el flujo priman sobre la etiqueta "Opcional"). La palabra "opcional" se lee como alcance mínimo: sin mecanismos avanzados (SSO, MFA).
- **Estado:** interpretado y adoptado. Si el profesor aclara lo contrario, se reabre.

### CON-002 · Monitoreo, drift simulado y segunda versión
- **Citado:** §11 lista de opcionales no menciona monitoreo ni drift; §12 (aceptación) exige #11 *"Promoción y rollback … entre dos versiones"*; §15.2 criterio 5 Excelente: *"monitoreo y drift simulado; segunda versión, promoción y rollback funcionando"*, Satisfactorio: *"rollback o monitoreo incompletos"*.
- **Impacto:** 15 % de la nota (criterio 5); la aceptación #11 es obligatoria.
- **Interpretación conservadora adoptada (P2-DEC-002):** segunda versión + promoción + rollback son **obligatorios** (aceptación #11); monitoreo y drift simulado se implementan para aspirar a Excelente en el criterio 5.
- **Estado:** interpretado y adoptado. El alcance mínimo de "drift simulado" se definirá en P2-9.4 con base en §15.2 c5 (no se elimina; se concreta).

### CON-003 · "Máximo 4 integrantes" vs. "los cuatro integrantes"
- **Citado:** §2.1: *"Grupos de máximo 4 estudiantes"* · §2.2: *"el historial de commits debe evidenciar contribuciones de los cuatro integrantes"* · §14: *"Los cuatro integrantes deben estar presentes"* · §15.2 criterio 8: *"contribuciones de los 4 integrantes visibles"*.
- **Impacto:** el grupo real tiene **1 integrante** (Mariana), por lo que tres frases del enunciado (§2.2, §14, c8) son imposibles de cumplir literalmente. §2.1 ("máximo 4") sí se cumple.
- **Interpretación conservadora adoptada (P2-DEC-003, actualizado):** no se inventan integrantes. La README declara el grupo real de 1 integrante con responsabilidades por frente de trabajo; el historial Git mostrará commits reales de esa única integrante. La diferencia con §2.2/§14/c8 se documenta en la README como limitación de composición del grupo y se plantea al profesor solo si surge en la sustentación (único caso en que la consulta es estrictamente necesaria).
- **Resolución de privacidad (P2-DEC-006):** al ser un repo público en GitHub, la identificación pública se limita al **nombre de pila "Mariana"** (sin apellidos, correo ni datos doxxing). El nombre completo, si el profesor lo exige en clase, se aporta por canal privado; no se versiona.
- **Estado:** [x] resuelto con la información real disponible.

### CON-004 · Estados de vencimiento ausentes de la tabla mínima
- **Citado:** §4 tabla de estados (6 estados, ninguno de vencimiento) vs. §4 párrafo final: *"si una reserva vence… el equipo define el nombre del estado o motivo"*.
- **Impacto:** la tabla dice "estados mínimos", por lo que añadir un estado/motivo de vencimiento es compatible.
- **Interpretación:** añadir estado `VENCIDA` (o `CANCELADA_POR_VENCIMIENTO`) documentado en la máquina de estados. Sin conflicto real; se registra para no perderlo.

### CON-005 · Diccionario de datos inexistente
- **Citado:** §7: *"El diccionario de datos explica unidades, categorías y valores faltantes"* — pero no hay archivo de diccionario entre los entregables adjuntos.
- **Impacto:** no podemos citar un diccionario oficial; se prohíbe inventarlo.
- **Interpretación (supuesto P2-SUP-001, adoptada):** construir un diccionario **derivado** de los CSV y el enunciado, marcado explícitamente como derivado (no oficial).

## 7. Supuestos (P2-SUP)

- **P2-SUP-001:** No existe diccionario de datos oficial adjunto; se elaborará uno derivado de los CSV y §7 del enunciado, identificado como "derivado, no oficial". → adoptado (no se dispone de otra fuente).
- **P2-SUP-002:** El directorio `C:\Users\maria\Downloads\CrediMarket` está vacío → CrediMarket P2 es un repo nuevo (git init), sin mezcla con P1 (`liga-de-apuestas` existe en Downloads pero no se toca).
- **P2-SUP-003:** Docker Desktop está instalado pero el daemon está apagado; se necesitará iniciarlo antes de P2-2.
- **P2-SUP-004:** Python 3.14.2 puede no tener soporte en todas las librerías ML (scikit-learn/mlflow/pycaret). **Verificar compatibilidad antes de fijar dependencias** en P2-2.2; no se fijarán versiones sin comprobarlo.
- **P2-SUP-005:** pandas no está instalado en el entorno actual; la inspección de P2-0 se hizo con librería estándar. Instalaciones futuras se pedirán/verificarán por etapa.

## 8. Decisiones (P2-DEC)

- **P2-DEC-001:** Autenticación, roles y autorización en backend son **obligatorios** (interpreta CON-001; rúbrica §15.2 c6/c7 + §4 + §11 priman sobre las etiquetas "Opcional" de §9/§10).
- **P2-DEC-002:** Segunda versión + promoción + rollback obligatorios (aceptación #11); monitoreo y drift simulado incluidos en alcance (interpreta CON-002).
- **P2-DEC-003:** No se inventan integrantes; README queda con tabla lista para nombres reales (interpreta CON-003).
- **P2-DEC-004 (estructura del repo):** raíz `CrediMarket/` con `docs/`, `servicios/{productos,clientes,prestamos,inventario}/`, `frontend/`, `ml/`, `pruebas/`, `scripts/`, `docker-compose.yml`, `.env.example`, `README.md`. Un único repo compartido; sin mezcla con P1.
- **P2-DEC-005 (política Git):** rama `main`; commits pequeños y coherentes tras validar incrementos; `git add` con lista explícita de archivos (nunca `git add .`); sin secretos, venv, `node_modules`, cachés ni temporales; sin force push; artefactos de ML: scripts y manifiestos versionados, CSV de datos y ejecuciones MLflow conservados por hash + almacenamiento persistente (volúmenes), modelos exportados versionados por manifiesto.
- **P2-DEC-006 (identidad pública):** repo público en GitHub → identificación pública acotada al nombre de pila **"Mariana"** (sin apellidos, correo ni datos personales). Nombre completo solo por canal privado si el profesor lo exige; no se versiona.
- **P2-DEC-007 (estética de README):** los README y documentos finales usan la estética visual acordada (banners `capsule-render` con paleta `21182E`/`B78ADC`/`79D9CD`/`DE85B8`/`EEE6F5`, badges `shields.io` flat-square, separadores rect, footer waving). Imagen de proyecto: `https://64.media.tumblr.com/0ceaefa71b378b4e49ddbda86846b227/01b7e65d99474b79-e3/s2048x3072/2ae1ba514b7b56bfd165426a1b8f703e3d0e648a.pnj` (verificada HTTP 200, PNG, 1.637.403 bytes). Redacción: profesional y específica del proyecto; sin referencias al proceso de asistencia ni notas conversacionales.
- *Pendientes deliberadamente sin decidir:* broker (P2-1.3), stack de frontend, motor de BD, algoritmos finales.

**Arquitectura vigente (documental, aún no implementada):** ver §6 y P2-DEC-004.

## 9. Artefactos (P2-ART)

- **P2-ART-001:** `_enunciado_texto.txt` — texto completo extraído del DOCX (303 líneas), en `final parte 2\`. Transitorio; no versionar en el repo.
- **P2-ART-002:** Este registro maestro.

## 10. Bitácora

| Fecha | Evento |
|---|---|
| 2026-10-27 | P2-0.1–0.3 completados: DOCX leído (16 secciones + rúbrica), CSV inspeccionados con hashes y estadísticas calculadas, 50 requisitos registrados. |
| 2026-10-27 | Contradicciones CON-001..005 registradas; interpretadas como P2-DEC-001..003 sin eliminar requisitos (P2-0.4 cerrado por decisión del responsable). |
| 2026-10-27 | Entorno verificado: repo vacío no git; Docker daemon apagado; Python 3.14.2 sin pandas. |
| 2026-10-27 | Estructura (P2-DEC-004) y política Git (P2-DEC-005) adoptadas; P2-0.7 cerrado. |
| 2026-10-27 | Grupo real registrado: 1 integrante (Mariana). P2-0.6 cerrado. P2-DEC-006 (identidad pública acotada a nombre de pila) y CON-003 resuelto. Etapa P2-0 completa. |
| 2026-10-27 | README con identidad visual acordada (P2-DEC-007); imagen de proyecto verificada (HTTP 200). Commit `5e085cf`. |
