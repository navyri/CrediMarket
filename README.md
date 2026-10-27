<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=210&color=F8F2EF&text=CREDIMARKET&fontColor=D8455C&fontSize=62&fontAlignY=32&desc=Microservicios%2C%20mensajer%C3%ADa%2C%20Redis%20y%20MLOps%20%C2%B7%20Parte%202&descColor=2A1F26&descAlignY=58"/>
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
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=2A1F26"/>
</p>

## Equipo

| Integrante | Responsabilidades principales |
|---|---|
| **Mariana** | Servicios de Productos e Inventario + Redis; Clientes + seguridad + frontend; Préstamos + broker; datos + modelo + MLOps; documentación y sustentación. |

Grupo de un integrante. Por privacidad, solo se publica el nombre de pila.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=2A1F26"/>
</p>

## Estado del proyecto

| Etapa | Contenido | Estado |
|---|---|---|
| P2-0 | Lectura del enunciado, inspección de datos y registro de requisitos | ✅ |
| P2-1 | Diseño de responsabilidades, contratos y máquina de estados | ⏳ |
| P2-2 | Base reproducible: Docker Compose, bases de datos, broker, Redis, MLflow | ⏳ |
| P2-3 – P2-4 | Servicios y mensajería confiable | ⏳ |
| P2-5 – P2-7 | Datos, entrenamiento, exportación y servicio del modelo | ⏳ |
| P2-8 – P2-9 | Frontend, versiones y monitoreo | ⏳ |
| P2-10 – P2-12 | Pruebas de aceptación, entrega y sustentación | ⏳ |

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=2A1F26"/>
</p>

## Datos

| Archivo | Registros | Columnas | Uso |
|---|---|---|---|
| `prestamos_entrenamiento.csv` | 12.000 | 15 (etiqueta `incumplimiento_90d`) | Entrenamiento, validación y prueba |
| `solicitudes_nuevas.csv` | 200 | 14 (sin etiqueta) | Solo inferencia |

Distribución de la etiqueta en el histórico: 69,44 % clase 0 · 30,56 % clase 1. Los archivos no se
versionan en el repositorio; sus hash SHA-256 están registrados para verificación.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&height=6&color=2A1F26"/>
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer&color=F8F2EF" alt=""/>
</p>
