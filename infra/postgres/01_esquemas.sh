#!/bin/bash
# P2-2.3 · Bases lógicas separadas y credenciales restringidas (§3 reglas de arquitectura).
# Se ejecuta una sola vez en el primer arranque de PostgreSQL (docker-entrypoint-initdb.d).
# Una instancia física única (permitida por §3) con 4 esquemas y 4 usuarios que SOLO ven el suyo.
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE svc_productos WITH LOGIN PASSWORD '${PASSWORD_PRODUCTOS}';
    CREATE ROLE svc_clientes  WITH LOGIN PASSWORD '${PASSWORD_CLIENTES}';
    CREATE ROLE svc_prestamos WITH LOGIN PASSWORD '${PASSWORD_PRESTAMOS}';
    CREATE ROLE svc_inventario WITH LOGIN PASSWORD '${PASSWORD_INVENTORY}';

    CREATE SCHEMA productos;
    CREATE SCHEMA clientes;
    CREATE SCHEMA prestamos;
    CREATE SCHEMA inventario;

    ALTER SCHEMA productos  OWNER TO svc_productos;
    ALTER SCHEMA clientes   OWNER TO svc_clientes;
    ALTER SCHEMA prestamos  OWNER TO svc_prestamos;
    ALTER SCHEMA inventario OWNER TO svc_inventario;

    GRANT USAGE ON SCHEMA productos TO svc_productos;
    GRANT USAGE ON SCHEMA clientes TO svc_clientes;
    GRANT USAGE ON SCHEMA prestamos TO svc_prestamos;
    GRANT USAGE ON SCHEMA inventario TO svc_inventario;

    -- Ningún cruce entre esquemas: cada rol queda sin privilegios sobre los ajenos.
    REVOKE ALL ON SCHEMA productos, clientes, prestamos, inventario FROM PUBLIC;
EOSQL

echo "[init] esquemas y usuarios restringidos creados"
