# Diccionario de datos (derivado, no oficial)

> **Origen:** elaborado a partir de `prestamos_entrenamiento.csv` y
> `solicitudes_nuevas.csv` con inspección directa (conteos, rangos y faltantes
> calculados, no declarados). **No** sustituye a un diccionario oficial: no se
> adjuntó ninguno con el enunciado (supuesto **P2-SUP-001**). Las cifras
> coinciden con el análisis de `ml/datos/ficha_datos.json` (que guarda además
> el SHA-256 de la fuente).

## 1. Fuentes

| Archivo | Filas × columnas | Uso | Versión |
|---|---|---|---|
| `prestamos_entrenamiento.csv` | 12.000 × 15 | entrenamiento, validación y prueba (§8) | histórico con etiqueta |
| `solicitudes_nuevas.csv` | 200 × 14 | **solo inferencia** (§7): sin etiqueta, prohibido calcular métricas con él | posteriores a los IDs del histórico |

Los CSV **no se versionan** en el repo (`.gitignore`); se regeneran/leerán desde
la ruta original y sus hash SHA-256 están registrados en el registro interno y en
`ml/datos/ficha_datos.json`.

## 2. Columnas del histórico

Convención de moneda: **COP enteros** salvo indicación. `None`/vacío = faltante
legítimo (no se rellena fuera del `Pipeline`).

| Columna | Tipo | Unidad / categorías | Rango observado | Faltantes | ¿Predictora? |
|---|---|---|---|---|---|
| `solicitud_id` | texto | identificador único | 12.000 valores únicos (`SOL-…`) | 0 | **No** — trazabilidad |
| `cliente_id` | texto | identificador único | 12.000 valores únicos (1 fila por cliente) | 0 | **No** — trazabilidad |
| `ingresos_mensuales_cop` | entero | COP/mes | 1.400.000 – 28.000.000 | 0 | Sí |
| `obligaciones_mensuales_cop` | entero | COP/mes | 11.000 – 16.485.000 | 0 | Sí |
| `tipo_empleo` | texto | `dependiente` · `independiente` · `temporal` | 6.765 / 3.461 / 1.681 | **93** (vacío) | Sí (categórica) |
| `antiguedad_laboral_meses` | entero | meses | 0 – 240 | **91** | Sí |
| `meses_historial_crediticio` | entero | meses | 0 – 300 | **97** | Sí |
| `creditos_previos` | entero | número de créditos | 0 – 19 | 0 | Sí |
| `atrasos_previos_30d` | entero | número de atrasos | 0 – 12 | 0 | Sí |
| `porcentaje_pago_puntual` | decimal | % de pagos puntuales | 12,68 – 99,97 | **2.473** | Sí |
| `monto_solicitado_cop` | entero | COP | 500.000 – 15.000.000 | 0 | Sí |
| `plazo_meses` | entero | meses | {6, 12, 18, 24, 36} | 0 | Sí |
| `tasa_mensual_simulada` | decimal | tasa mensual simulada | **constante 0,0180** | 0 | **No** — excluida (constante) |
| `cuota_estimada_cop` | decimal | COP/mes | 18.991,92 – 2.659.841,03 | 0 | Sí |
| `incumplimiento_90d` | entero | **etiqueta**: 0 = pagó · 1 = incumplió a 90 días | 8.333 (69,44 %) / 3.667 (30,56 %) | 0 | **Nunca** como entrada (§7) |

### Notas por columna

- **`porcentaje_pago_puntual` vacío** = cliente sin historial crediticio previo
  (§7 lo permite). Se imputa **dentro** del `Pipeline` con la mediana ajustada
  solo con entrenamiento; nunca con valores de validación/prueba.
- **`tipo_empleo` vacío** (93 filas): se trata como categoría propia
  (`SimpleImputer(strategy="most_frequent")` + `OneHotEncoder(handle_unknown="ignore")`).
- **`tasa_mensual_simulada`** es idéntica en las 12.000 filas → variable sin
  poder discriminativo; se excluye de las predictorias (§7: "justifiquen la
  exclusión de variables constantes o redundantes"). La tasa que usa el servicio
  es un parámetro de configuración (`TASA_MENSUAL_SIMULADA`), no una lectura de
  la caché ni del modelo.
- **Identificadores** (`solicitud_id`, `cliente_id`) se conservan solo para
  trazabilidad, auditoría y deduplicación; el `Pipeline` recibe únicamente las
  11 predictorias (10 numéricas + `tipo_empleo`).

## 3. Columnas de `solicitudes_nuevas.csv`

Mismas 14 columnas **sin** `incumplimiento_90d`: 200 filas con IDs continuos
posteriores (`SOL-0012001+`), **0 solapamiento** de `solicitud_id` y `cliente_id`
con el histórico. Faltantes: `porcentaje_pago_puntual` 43 · `tipo_empleo` 2 ·
`antiguedad_laboral_meses` 1 · `meses_historial_crediticio` 1.
Sirve para probar inferencia y monitoreo de deriva (`scripts/monitoreo/demostrar_drift.py`).

## 4. Particiones (§8.A)

Estratificadas por la etiqueta, **semilla 42**, sin solapamiento de IDs:

| Partición | Filas | Tasa de clase 1 | Uso |
|---|---|---|---|
| `ml/datos/entrenamiento.csv` | 7.200 | ≈ 30,55 % | ajuste de preprocesamiento y modelos |
| `ml/datos/validacion.csv` | 2.400 | ≈ 30,55 % | selección de candidato y umbral |
| `ml/datos/prueba.csv` | 2.400 | ≈ 30,55 % | evaluación final, una sola vez |

## 5. Etiqueta y objetivo

- Objetivo: **`incumplimiento_90d`** (clase positiva 1 = incumplió a 90 días).
- Los registros son **préstamos simulados con resultado conocido**, no
  solicitudes rechazadas: el modelo estima riesgo y la decisión la toma una
  política documentada (regla de control + umbral). No se entrena para predecir
  una columna de aprobación.
- Desbalance moderado (≈30,6 % clase 1): por eso la selección no se hace por
  accuracy (ver `docs/informe-seleccion-modelo.md`).
