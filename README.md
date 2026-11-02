<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=210&color=D8455C&text=CREDIMARKET&fontColor=F8F2EF&fontSize=62&fontAlignY=32&desc=Microservicios%2C%20mensajer%C3%ADa%2C%20Redis%20y%20MLOps%20%C2%B7%20Parte%202&descColor=D8455C&descAlignY=58"/>
</p>

<p align="center">
  <img src="https://64.media.tumblr.com/0ceaefa71b378b4e49ddbda86846b227/01b7e65d99474b79-e3/s2048x3072/2ae1ba514b7b56bfd165426a1b8f703e3d0e648a.pnj" alt="CrediMarket" height="320"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/microservicios-4%20de%20negocio-D8455C?style=flat-square"/>
  <img src="https://img.shields.io/badge/Python-REST-2A1F26?style=flat-square&logo=python&logoColor=F8F2EF"/>
  <img src="https://img.shields.io/badge/Redis-cache--aside-F2C4CC?style=flat-square&logo=redis&logoColor=2A1F26"/>
  <img src="https://img.shields.io/badge/broker-Kafka%20o%20RabbitMQ-9FB8DC?style=flat-square"/>
  <img src="https://img.shields.io/badge/MLflow-experimentos-2A1F26?style=flat-square&logo=mlflow&logoColor=D8455C"/>
  <img src="https://img.shields.io/badge/Docker-Compose-9FB8DC?style=flat-square&logo=docker&logoColor=2A1F26"/>
  <img src="https://img.shields.io/badge/datos-12.000%2B200%20sint%C3%A9ticos-D8455C?style=flat-square"/>
</p>

**CrediMarket** es una tienda que vende computadores, celulares y otros productos tecnológicos a
crédito. El proyecto reemplaza la aplicación monolítica que aprueba dos créditos por el mismo último
computador con una arquitectura de cuatro microservicios —**Productos**, **Clientes**, **Préstamos** e
**Inventario**— coordinados por un broker de mensajería, con caché Redis en el catálogo y un modelo de
ML que estima el riesgo de incumplimiento de cada solicitud con trazabilidad completa en MLflow.

Préstamos obtiene la cotización vigente por API, ejecuta el pipeline de ML exportado y pasa por los
estados `PENDIENTE_INVENTARIO` → `APROBADA` → `COMPLETADA`; la aprobación solo ocurre cuando
Inventario confirma la reserva de forma atómica. El frontend consume las APIs reales y la
demostración se hace desde el navegador con datos persistidos.

Los datos y las operaciones de crédito son sintéticos y académicos. No constituyen una política
financiera aplicable a personas reales.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Arquitectura

Cuatro microservicios de negocio, cada uno dueño de su esquema en una única instancia de
PostgreSQL; la coordinación es por API y por mensajería, nunca por tablas ajenas.

| Servicio | Tecnología | Puerto | Responsabilidad |
|---|---|---|---|
| **Productos** | Python · FastAPI | 8001 | Catálogo con caché Redis *cache-aside* (`productos:v1:{id}`, TTL 60 s) |
| **Clientes** | Python · FastAPI | 8002 | Cuentas, roles, ficha y perfil financiero, importación CSV idempotente |
| **Préstamos** | Python · FastAPI | 8003 | Solicitud idempotente, modelo de riesgo y ciclo MLOps (MLflow) |
| **Inventario** | Python · FastAPI | 8004 | Reserva atómica de la última unidad, entregas y vencimientos |
| **Frontend** | React 19 · Vite · nginx | **8090** | Interfaz obligatoria: consume solo las APIs (sin secretos en el código) |

Infraestructura (no cuenta como servicios): **RabbitMQ** `credimarket.topic` con DLX
`credimarket.dlx` (5672/15672) · **Redis** (6379) · **PostgreSQL 17** con un esquema por
servicio (5434) · **MLflow** con volumen persistente (5000).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Puesta en marcha

Desde un clon limpio (requisitos: Docker con Compose):

```bash
git clone https://github.com/navyri/CrediMarket.git
cd CrediMarket
cp .env.example .env      # revisar secretos: JWT_SECRET, contraseñas, CORS_ORIGINS
docker compose up -d      # 9 contenedores: 4 servicios + frontend + infraestructura
```

| Componente | URL |
|---|---|
| Frontend (demo desde el navegador) | http://localhost:8090 |
| APIs Productos · Clientes · Préstamos · Inventario | :8001 · :8002 · :8003 · :8004 |
| MLflow · RabbitMQ management · PostgreSQL · Redis | :5000 · :15672 · :5434 · :6379 |

Cuentas de prueba y los 8 escenarios de la demostración están en
[`docs/guia-demo.md`](docs/guia-demo.md). Los experimentos de MLflow sobreviven a los
reinicio gracias al volumen `mlflowdata`; los datos viven en `pgdata`.

Para desarrollo del frontend sin contenedor: `cd frontend && npm ci && npm run dev`
(variables `VITE_API_*` en `frontend/.env.example`).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Pruebas

```bash
pip install -r servicios/requirements-dev.txt   # pytest + httpx (una sola vez)
python scripts/ejecutar_pruebas.py              # 123 pruebas: unitarias + integración
python scripts/aceptacion/ejecutar_todas.py     # 16 casos de §12 → 16/16 OK (~80 s)
python scripts/medir_cache.py                   # mediciones de la caché Redis
```

Las pruebas de integración corren contra el Compose real (PostgreSQL, RabbitMQ, Redis y
modelo exportado), sin mocks de infraestructura. Los casos de aceptación detienen y
reinician contenedores en pruebas de caída, por eso el orquestador es secuencial.
Resultados por caso: [`docs/evidencias/aceptacion/`](docs/evidencias/aceptacion/).

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Equipo

| Integrante | Responsabilidades principales |
|---|---|
| **Mariana** | Servicios de Productos e Inventario + Redis; Clientes + seguridad + frontend; Préstamos + broker; datos + modelo + MLOps; documentación y sustentación. |

Grupo de un integrante. Por privacidad, solo se publica el nombre de pila.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Datos

| Archivo | Registros | Columnas | Uso |
|---|---|---|---|
| `prestamos_entrenamiento.csv` | 12.000 | 15 (etiqueta `incumplimiento_90d`) | Entrenamiento, validación y prueba |
| `solicitudes_nuevas.csv` | 200 | 14 (sin etiqueta) | Solo inferencia |

Distribución de la etiqueta en el histórico: 69,44 % clase 0 · 30,56 % clase 1. Los archivos no se
versionan en el repositorio; sus hash SHA-256 están registrados para verificación.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=D8455C"/>
</p>

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/guia-demo.md`](docs/guia-demo.md) | Cuentas de prueba y pasos de la demostración desde el navegador |
| [`docs/informe-redis-desempeno.md`](docs/informe-redis-desempeno.md) | Diseño de la caché, mediciones (MISS/HIT/carga), fallos y recursos |
| [`docs/arquitectura/diagramas.md`](docs/arquitectura/diagramas.md) | Diagrama de arquitectura y de secuencia |
| [`docs/arquitectura/contratos-rest.md`](docs/arquitectura/contratos-rest.md) | Contratos de las 4 APIs (incluye la convención de errores) |
| [`docs/arquitectura/contratos-mensajes.md`](docs/arquitectura/contratos-mensajes.md) | Contratos y ejemplos JSON de los mensajes |
| [`docs/arquitectura/maquina-estados.md`](docs/arquitectura/maquina-estados.md) | Máquina de estados T1–T9 y tiempos de espera |
| [`docs/arquitectura/decision-broker.md`](docs/arquitectura/decision-broker.md) | Decisión Kafka vs. RabbitMQ y su configuración |
| [`docs/arquitectura/seguridad.md`](docs/arquitectura/seguridad.md) | JWT, roles, autorización e idempotencia |
| [`docs/arquitectura/estrategia-pruebas.md`](docs/arquitectura/estrategia-pruebas.md) | Estrategia de pruebas y mapa a la rúbrica |

## Estructura

```text
CrediMarket/
├── docker-compose.yml        # frontend + 4 servicios + broker + Redis + BD + MLflow
├── .env.example              # configuración y secretos de ejemplo (copiar a .env)
├── servicios/                # Productos, Clientes, Préstamos e Inventario (FastAPI)
│   ├── requirements-base.txt # dependencias reproducibles de los servicios
│   ├── requirements-dev.txt  # pytest + httpx para las pruebas
│   └── prestamos/requirements.txt  # dependencias de inferencia del modelo
├── frontend/                 # React 19 + Vite (build de producción empaquetado en nginx)
├── ml/                       # prep, train, export, monitoreo, datos y modelos (v1/v2)
│   └── requirements.txt      # dependencias del ciclo MLOps
├── scripts/                  # pruebas pytest, casos de aceptación y mediciones
└── docs/                     # arquitectura, guía de demo, informes y evidencias
```

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer&color=D8455C" alt=""/>
</p>
