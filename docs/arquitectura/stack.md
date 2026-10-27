# P2-DEC-010 · Stack tecnológico

Decisión de P2-1.2. Verificaciones hechas en este entorno antes de fijar versiones (SUP-004).

## Verificación ejecutada

| Paquete | Verificación | Resultado |
|---|---|---|
| scikit-learn | `pip list` | 1.9.1 instalado |
| numpy / scipy | `pip list` | 2.5.4 / 1.18.1 instalados |
| fastapi / uvicorn / pydantic | `pip list` | 0.141.1 / 0.54.0 / 2.13.5 instalados |
| SQLAlchemy / psycopg | `pip list` | 2.1.5 / 3.3.6 instalados |
| pandas 3.1.0 | `pip install --dry-run` | wheel `cp314-win_amd64` disponible |
| mlflow 3.17.2 | `pip install --dry-run` | resuelve en cp314 (exit 0) |
| redis 8.1.0 · alembic 1.20.1 · pytest 9.1.1 · aio-pika 10.2.1 · matplotlib 3.11.2 | `pip install --dry-run` | todos resuelven (exit 0) |
| React 19.3.1 · Vite 8.3.5 · @vitejs/plugin-react 6.1.2 | `npm view` | disponibles con Node 24.13.0 / npm 11.6.2 |

## Stack elegido

| Capa | Elección | Versión fijada (requirements.txt / package.json) |
|---|---|---|
| Lenguaje servicios | Python 3.14 | 3.14.2 (entorno local y base `python:3.14-slim` en Compose) |
| API (los 4 servicios) | FastAPI + uvicorn | fastapi 0.141.1, uvicorn 0.54.0, pydantic 2.13.5 |
| ORM/migraciones | SQLAlchemy 2 + Alembic | sqlalchemy 2.1.5, alembic 1.20.1, psycopg 3.3.6 |
| Base de datos | PostgreSQL (una instancia, 4 esquemas lógicos, 4 usuarios con credenciales restringidas por esquema) | imagen `postgres:17-alpine` (§3 permite instancia única con separación lógica) |
| Caché | Redis | imagen `redis:8-alpine`, cliente `redis 8.1.0` |
| Broker | **RabbitMQ** — ver `decision-broker.md` | imagen `rabbitmq:4-management-alpine`, cliente `aio-pika 10.2.1` |
| Frontend | React 19 + Vite 8 + TypeScript | react 19.3.1, vite 8.3.5, plugin-react 6.1.2 |
| ML | scikit-learn 1.9.1 + pandas 3.1.0 + joblib 1.6.0 | ya instalados / verificados |
| Tracking | MLflow Tracking (infraestructura) | mlflow 3.17.2, artefactos y backend en volumen persistente |
| Pruebas Python | pytest + httpx (TestClient) | pytest 9.1.1, httpx 0.28.1 |

Justificación breve: FastAPI satisface la restricción §3 de Préstamos en Python; usarlo en los cuatro
servicios unifica contratos (OpenAPI automático), dependencias y pruebas sin crear abstracciones
nuevas. PostgreSQL permite la instancia única con esquemas separados exigida en la interpretación de
§3. Node 24 con Vite 8 está disponible en el entorno (verificado con `npm view`), por lo que el
frontend no requiere instalación de otro runtime.

Pinned en `servicios/*/requirements.txt` y `frontend/package.json` en P2-2.2.
