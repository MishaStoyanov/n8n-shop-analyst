#!/bin/bash
# The agents connect as analyst_ro: it can read the shop data and nothing else.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE analyst_ro LOGIN PASSWORD '${ANALYST_RO_PASSWORD}';
GRANT CONNECT ON DATABASE shop TO analyst_ro;
GRANT USAGE ON SCHEMA public TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
ALTER ROLE analyst_ro SET default_transaction_read_only = on;
ALTER ROLE analyst_ro SET statement_timeout = '10s';
SQL
