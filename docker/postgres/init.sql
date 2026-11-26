CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
BEGIN;
\i /docker-init-resources/solar_handoff.sql
COMMIT;
