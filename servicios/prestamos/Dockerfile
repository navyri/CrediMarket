# Servicio Préstamos (P2-7) — build desde la raíz del repo:
#   docker build -f servicios/prestamos/Dockerfile .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY servicios/requirements-base.txt /tmp/requirements-base.txt
# El requirements de Préstamos incluye `-r ../requirements-base.txt`: se
# conserva la estructura relativa para que pip lo resuelva dentro de la imagen.
COPY servicios/prestamos/requirements.txt /tmp/prestamos/requirements.txt
RUN pip install --no-cache-dir -r /tmp/prestamos/requirements.txt

COPY servicios/prestamos/app ./app
COPY servicios/prestamos/alembic ./alembic
COPY servicios/prestamos/alembic.ini ./alembic.ini

# El modelo activo se sirve desde el volumen montado /modelos (§8.D): la
# promoción y el rollback persisten fuera del contenedor.
EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
