#!/bin/bash
# Incident log for the error-handler workflow, written by ops_writer, which may only insert there.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE SCHEMA ops;
CREATE TABLE ops.incidents (
    id            SERIAL PRIMARY KEY,
    happened_at   TIMESTAMP NOT NULL DEFAULT now(),
    workflow_name TEXT,
    failed_node   TEXT,
    error_message TEXT,
    execution_url TEXT
);
CREATE ROLE ops_writer LOGIN PASSWORD '${OPS_WRITER_PASSWORD}';
GRANT USAGE ON SCHEMA ops TO ops_writer;
GRANT INSERT, SELECT ON ops.incidents TO ops_writer;
GRANT USAGE ON SEQUENCE ops.incidents_id_seq TO ops_writer;
SQL
