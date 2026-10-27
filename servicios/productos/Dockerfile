# Servicio Productos (P2-3) — build desde la raíz del repo:
#   docker build -f servicios/productos/Dockerfile .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY servicios/requirements-base.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY servicios/productos/app ./app
COPY servicios/productos/alembic ./alembic
COPY servicios/productos/alembic.ini ./alembic.ini

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
