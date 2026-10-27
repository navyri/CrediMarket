# Servicio Inventario (P2-4) — build desde la raíz del repo:
#   docker build -f servicios/inventario/Dockerfile .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY servicios/requirements-base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY servicios/inventario/app ./app
COPY servicios/inventario/alembic ./alembic
COPY servicios/inventario/alembic.ini ./alembic.ini

EXPOSE 8004
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
