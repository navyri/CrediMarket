# Informe de selección del modelo (entregable 4)

**Requisito:** §8.B «Entrenar y comparar» · `P2-REQ-030`, `P2-REQ-031`, `P2-REQ-032`.
**Objetivo:** estimar `incumplimiento_90d` (solicitud que incumple a 90 días) sobre el
histórico sintético de CrediMarket. Los datos y las operaciones de crédito son
ficticios: las probabilidades **no** representan el riesgo real de personas.

Comandos que regeneran todo lo documentado aquí:

```bash
python ml/prep/preparar_datos.py            # particiones (semilla 42)
python ml/train/entrenar.py --modelo-version v2
python scripts/ml/exportar_experimentos.py  # historial de MLflow → JSON
```

## 1. Reglas declaradas ANTES de comparar

| Decisión | Valor declarado | Dónde vive |
|---|---|---|
| Particiones (70/15/15 aprox.) | 7.200 entrenamiento · 2.400 validación · 2.400 prueba | `ml/datos/*.csv`, `ficha_datos.json` |
| Semilla | `42` (corridas reproducibles) | `SEMILLA` en `ml/train/entrenar.py` |
| Métrica de selección | **ROC-AUC en validación** | `MÉTRICA_SELECCIÓN` |
| Criterio de desempate | mayor ROC-AUC → menor **Brier** en validación → orden de la parrilla | comentario en el bucle de selección, parámetro `desempate` en MLflow |
| Métrica del umbral | **F1 máximo en validación** (`MÉTRICA_UMBRAL`) | barrido fijo `0.05 … 0.95` |
| Costos ficticios (justificación del umbral) | `C_falso_aprobar = 100` · `C_falso_rechazar = 25` | `COSTO_FALSO_*`, antes del barrido |
| Uso de la prueba | evaluada **una sola vez**, al final | §8.B |

Además: el preprocesamiento (imputación, escalado, one-hot) se ajusta **solo** con
entrenamiento dentro del `sklearn.Pipeline`; `solicitud_id`, `cliente_id` y la
etiqueta nunca entran como variables; no se selecciona por accuracy (se reporta,
pero no decide).

## 2. Baseline y parrilla de candidatas (iteración v2)

**1 baseline trivial + 7 corridas candidatas = 8 ejecuciones**, sobre 3 familias de
algoritmos (§8.B pide baseline + ≥3 algoritmos + ≥6 corridas candidatas):

| Candidato | Hiperparámetros | ROC-AUC ↑ | AP ↑ | Brier ↓ | Precision | Recall | F1 | Matriz TN/FP/FN/TP |
|---|---|---|---|---|---|---|---|---|
| `baseline_prior` (trivial) | strategy=prior | 0.5000 | 0.3058 | 0.2123 | 0.0000 | 0.0000 | 0.0000 | 1666/0/734/0 |
| `regresion_logistica_C01` | C=0.1 | 0.7046 | **0.5276** | 0.2167 | 0.4635 | 0.6226 | 0.5314 | 1137/529/277/457 |
| **`regresion_logistica`** ★ | C=1.0 | **0.7047** | 0.5273 | 0.2166 | 0.4638 | 0.6281 | **0.5336** | 1133/533/273/461 |
| `regresion_logistica_C10` | C=10 | 0.7047 | 0.5273 | 0.2166 | 0.4632 | 0.6267 | 0.5327 | 1133/533/274/460 |
| `random_forest` | n=300, leaf=2 | 0.6701 | 0.4926 | **0.1952** | 0.5816 | 0.2670 | 0.3660 | 1525/141/538/196 |
| `random_forest_profundo` | n=500, depth=14, leaf=1 | 0.6677 | 0.4880 | 0.1980 | 0.5656 | 0.2643 | 0.3603 | 1517/149/540/194 |
| `hist_gradient_boosting` | iter=300, lr=0.08 | 0.6569 | 0.4874 | 0.2015 | 0.5631 | 0.3038 | 0.3947 | 1493/173/511/223 |
| `hist_gradient_boosting_conservador` | iter=500, lr=0.05, leaf=30 | 0.6558 | 0.4898 | 0.2019 | 0.5383 | 0.2875 | 0.3748 | 1485/181/523/211 |

Métricas sobre **validación** (2.400 filas), umbral de referencia 0.5.
Los hiperparámetros variaron con justificación: regularización de la logística
(C ∈ {0,1; 1; 10} → mayor C = menos penalización), profundidad y número de ároboles
del bosque, e iteraciones/tasa del potenciador (más paciente vs. más fiel).

**Lectura:**

- El baseline trivial se queda en ROC-AUC 0.5000 y AP 0.3058 (exactamente la
  proporción de clase 1: 734/2.400) y no aprueba **nada** con `class_weight`
  ausente → F1 = 0. **Todo algoritmo real lo supera de forma holgada.**
- La logística gana en la métrica declarada (0.7047) y también en F1 (0.5336).
- Los bosques y el potenciador tienen el **mejor Brier** (0.195–0.202, mejor
  calibración) pero mucho peor recall (0.26–0.30): con `class_weight=balanced`
  sobreestiman la clase mayoritaria y solo aprueban a los de riesgo muy bajo.
  Como no se selecciona por accuracy ni por Brier solo, quedan fuera.
- Desempate: `regresion_logistica` (0.7047424) > `regresion_logistica_C10`
  (0.7047244) > `regresion_logistica_C01` (0.7046009): **no hubo empate exacto**,
  el criterio declarado no llegó a desempatar.

**Ganador: `regresion_logistica`** (ROC-AUC 0.7047 en validación).

## 3. Umbral: ajustado en validación y congelado antes de la prueba

Barrido de 91 umbrales sobre validación con el candidato ganador:

- **Umbral servido: `0.49`** = máximo F1 en validación (F1 = 0.5363).
  Se congela aquí y **no se toca** al evaluar en prueba.

### Curva de costos ficticios (justificación, §8.B)

Costo(u) = `100 · FP(u)` + `25 · FN(u)`, con los dos errores distinguidos:

- **aprobar a quien incumplirá** (`FP`, costo 100): la pérdida simulada del crédito;
- **rechazar a quien habría pagado** (`FN`, costo 25): el margen que no se cobra.

| Umbral | FP (aprobar mal) | FN (rechazar bien) | Costo ficticio |
|---|---|---|---|
| 0.45 | 758 | 199 | 80.775 |
| **0.49 (servido)** | **576** | **254** | **63.950** |
| 0.50 | 533 | 273 | 60.125 |
| 0.60 | 230 | 447 | 34.175 |
| 0.70 | 86 | 576 | 23.000 |
| 0.80 | 26 | 668 | 19.300 |
| **0.89 (mínimo)** | **2** | **718** | **18.150** |
| 0.90 | 2 | 722 | 18.250 |

**Decisión documentada.** Con estos pesos el mínimo de la curva cae en **0.89**,
pero ese punto aprueba solo **18 de 2.400** solicitudes (0,75 %: 16 verdaderos
positivos y 2 falsos positivos) y rechaza a 718 clientes que sí pagarían: es la
solución «no conceder casi nada», inútil para un prestamista. Los pesos son
**ficticios y declarados a priori**, no una recomendación financiera; la curva se
publica como análisis de sensibilidad, no como política.

Por eso se sirve el umbral **0.49** de la métrica declarada (F1), que en
validación aprueba 1.056 de 2.400 solicitudes (44 %) con recall 0.65 sobre los
incumplimientos: equilibra los dos errores en lugar de anular uno. El umbral de
costo mínimo queda registrado igualmente (`umbral_costo_minimo = 0.89`,
`val_costo_ficticio_min = 18150`) para que la decisión sea reproducible.

## 4. Evaluación final en prueba (una sola vez)

Tras congelar candidato y umbral, el pipeline se reajusta con el conjunto de
desarrollo completo (entrenamiento + validación) y se evalúa **una sola vez** en
las 2.400 filas de prueba con umbral 0.49:

| Métrica | Valor |
|---|---|
| ROC-AUC | **0.6954** |
| Average precision (AP) | 0.5318 |
| Brier (calibración) | 0.2179 |
| Precision (clase 1) | 0.4390 |
| Recall (clase 1) | 0.6289 |
| F1 (clase 1) | 0.5171 |
| Accuracy (informativo, no decide) | 0.6413 |
| Matriz de confusión | TN 1078 · FP 589 · FN 272 · TP 461 |

- La AP de prueba (0.5318) queda sobre la base de clase de prueba (≈0.3058):
  el modelo aporta señal real sobre el azar, sin pretender calibrar riesgo real.
- Entre validación (0.7047) y prueba (0.6954) la caída es de 0,009: sin
  indicios de sobreajuste.
- Con el umbral congelado se rechazan 272 clientes que habrían pagado (FN) y se
  aprueban 589 que incumplirán (FP); con los costos ficticios del §3 eso sería
  63.950 en validación y 65.700 en prueba (`100·589 + 25·272`).

## 5. Trazabilidad (MLflow, §8.C)

- Experimento `credimarket-incumplimiento-90d` en http://localhost:5000
  (volumen `mlflowdata`): **59 corridas** en total (61 con
  `credimarket-monitoreo`), de las cuales **9 son el lote de esta comparación**
  (8 candidatas + `v2-seleccion`).
- Run de selección: `b3bd8708780843aca67c603880c3a6bb` con los parámetros
  `candidato_ganador`, `metrica_seleccion`, `desempate`, `metrica_umbral`,
  `umbral`, `umbral_costo_minimo`, `costo_falso_*` y las métricas `val_*` y `test_*`.
- Corridas del lote: `dc888d2d…` (baseline), `040f6fed…` (C01), `c2aca2e7…`
  (ganadora), `0c7c765a…` (C10), `2043e4ec…` (bosque), `ba969e9c…`
  (bosque profundo), `86d6b712…` (potenciador), `5c3cca19…` (conservador).
- Artefactos por corrida: parámetros, métricas, importancia de variables y el
  `Pipeline` completo. Artefactos del lote de selección:
  `importancias.csv`, `curva_costos_validacion.csv` y el modelo registrado como
  `credimarket-incumplimiento` (versión 5).
- Historial exportado a `docs/evidencias/experimentos_mlflow.json`
  (`python scripts/ml/exportar_experimentos.py`).
- Manifiesto del modelo: `ml/modelos/v2/metadatos.json` (+ `modelo.joblib`,
  `importancias.csv`, `curva_costos_validacion.csv`); promoción/rollback con
  `python ml/export/administrar_activo.py` y trazas en
  `ml/modelos/historial_promociones.jsonl`.

## 6. Versión activa y relación con v1

La versión **activa sigue siendo `v1`** (run `709931de…`, umbral 0.49): no se
promueve un modelo nuevo sin necesidad y los 16 casos de aceptación siguen
validando el artefacto en producción (`caso_10` compara API vs `modelo.joblib`;
`caso_11` ejercita promoción/rollback v1 ↔ v2 y restaura el estado).

La v2 fue entrenada con la parrilla completa de §8.B y **reproduce exactamente
las métricas de la v1** (mismo ganador `regresion_logistica`, mismos datos,
misma semilla y mismo umbral 0.49: ROC-AUC 0.6954, F1 0.5171), de modo que
promoverla más adelante no cambiaría el comportamiento del servicio. Lo que la
v2 aporta es la comparación completa (baseline + 7 candidatas), las métricas
ampliadas (AP, Brier, matriz de confusión) y la curva de costos exigidos por
§8.B.

## 7. Limitaciones

- Datos sintéticos y desbalanceados (≈30,6 % clase 1): los umbrales y costos son
  ejercicios académicos, **no** una política de crédito aplicable a personas.
- Una sola partición con semilla fija (reproducibilidad) en lugar de
  validación cruzada; el enunciado admite «validación o validación cruzada
  dentro del conjunto de desarrollo».
- La calibración se evalúa con Brier (punto único); una curva de calibración
  completa quedaría como extensión opcional.
