# Diagramas de arquitectura y secuencia

Diseño de P2-1.9. Se versionan como Mermaid (se renderizan en GitHub y se actualizan con el
código).

## 1. Arquitectura general

```mermaid
flowchart TB
    subgraph Cliente
        NAV[Navegador · frontend React]
    end

    subgraph Servicios_de_negocio["Servicios de negocio (4)"]
        PROD[Productos :8001<br/>FastAPI · esquema productos]
        CLI[Clientes :8002<br/>FastAPI · esquema clientes<br/>auth + importación CSV]
        PRE[Préstamos :8003<br/>FastAPI · esquema prestamos<br/>modelo ML + MLflow client]
        INV[Inventario :8004<br/>FastAPI · esquema inventario]
    end

    subgraph Infraestructura
        PG[(PostgreSQL 17<br/>4 esquemas · 4 usuarios)]
        REDIS[(Redis 8<br/>solo Productos)]
        RABBIT[[RabbitMQ 4<br/>credimarket.topic + dlx]]
        MLFLOW[[MLflow Tracking<br/>volumen persistente]]
    end

    NAV -->|REST + JWT| PROD
    NAV -->|REST + JWT| CLI
    NAV -->|REST + JWT| PRE
    NAV -->|REST + JWT| INV

    PROD --- PG
    CLI --- PG
    PRE --- PG
    INV --- PG
    PROD <-->|cache-aside| REDIS

    PRE -->|comandos| RABBIT
    INV -->|eventos| RABBIT
    PRE <-->|tracking + artefactos| MLFLOW

    PRE -->|GET cliente (token servicio)| CLI
    PRE -->|GET cotización (token servicio)| PROD
```

Reglas visibles: el navegador toca solo APIs; ningún servicio cruza esquemas (las líneas `---` son
posesión individual del mismo motor); el broker solo conecta Préstamos↔Inventario; Redis solo vive
en Productos; MLflow es infraestructura consumida por Préstamos y por el proceso de entrenamiento
fuera de línea.

## 2. Secuencia · caso feliz (solicitud → reserva → aprobación → entrega)

```mermaid
sequenceDiagram
    autonumber
    actor U as Cliente (navegador)
    participant P as Préstamos
    participant C as Clientes
    participant PR as Productos
    participant B as RabbitMQ
    participant I as Inventario

    U->>P: POST /prestamos (Idempotency-Key)
    P->>C: GET /clientes/{id} (token servicio)
    C-->>P: datos + activo
    P->>PR: GET /productos/{id}/cotizacion
    PR-->>P: precio + version
    P->>P: pipeline ML → favorable
    P->>P: transacción: préstamo + outbox(reserva.solicitada)
    P-->>U: 202 {prestamo_id, estado:PENDIENTE_INVENTARIO}
    P->>B: outbox → publica (confirm)
    B->>I: prestamo.reserva.solicitada
    I->>I: UPDATE atómico (disponible >= n) + outbox + ack
    B->>P: inventario.reserva.reservada
    P->>P: PENDIENTE_INVENTARIO → APROBADA (commit, ack)
    U->>P: GET /prestamos/{id} (polling)
    P-->>U: APROBADA
    actor A as Administrador
    A->>I: POST /reservas/{id}/entrega
    I->>I: salida + outbox + ack
    B->>P: inventario.salida.confirmada
    P->>P: APROBADA → COMPLETADA
    A->>P: GET /prestamos/{id}
    P-->>A: COMPLETADA
```

## 3. Secuencia · rechazo por riesgo (sin inventario)

```mermaid
sequenceDiagram
    autonumber
    actor U as Cliente (navegador)
    participant P as Préstamos
    participant B as RabbitMQ
    participant I as Inventario

    U->>P: POST /prestamos (Idempotency-Key)
    P->>P: pipeline ML → desfavorable
    P->>P: RECHAZADA + modelo_version + umbral
    P-->>U: 201 {prestamo_id, estado:RECHAZADA, motivo}
    Note over P,B: ningún mensaje hacia Inventario
    B-->>I: (sin tráfico)
```

## 4. Secuencia · cancelación con evento tardío (prueba #7)

```mermaid
sequenceDiagram
    autonumber
    actor U as Cliente
    participant P as Préstamos
    participant B as RabbitMQ
    participant I as Inventario

    U->>P: POST /prestamos/{id}/cancelar
    P->>P: APROBADA → (espera) outbox(reserva.cancelada)
    P->>B: prestamo.reserva.cancelada
    B->>I: prestamo.reserva.cancelada
    I->>I: libera reserva (transacción)
    I->>B: inventario.reserva.liberada
    B->>P: inventario.reserva.liberada
    P->>P: → CANCELADA (final)
    Note over B,P: retraso: llega tarde inventario.reserva.reservada
    B->>P: inventario.reserva.reservada (tardío)
    P->>P: estado final → log evento_tardio_ignorado (sin reactivar)
```

## 5. Secuencia · vencimiento de reserva (§4)

```mermaid
sequenceDiagram
    autonumber
    participant T as Tarea periódica (Inventario)
    participant I as Inventario
    participant B as RabbitMQ
    participant P as Préstamos

    Note over I: reserva RESERVADA con vence_en < now()
    T->>I: cada 30 s
    I->>I: transacción: reservada→vencida + unidades disponibles + outbox
    I->>B: inventario.reserva.vencida
    B->>P: inventario.reserva.vencida
    P->>P: APROBADA → CANCELADA_VENCIDA (nunca aprobado sin reserva)
```
