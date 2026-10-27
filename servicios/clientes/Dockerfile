# Servicio Clientes (P2-3) — build desde la raíz del repo:
#   docker build -f servicios/clientes/Dockerfile .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY servicios/requirements-base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY servicios/clientes/app ./app
COPY servicios/clientes/alembic ./alembic
COPY servicios/clientes/alembic.ini ./alembic.ini

EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
