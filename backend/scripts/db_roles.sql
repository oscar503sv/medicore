-- Database roles for Medicore: a schema owner and a DML-only application role.
--
--   medicore_owner  owns every object in `public`; runs migrations and the demo purge.
--   medicore_app    what the API connects as: SELECT/INSERT/UPDATE/DELETE and nothing else.
--                   It cannot alter the schema, lift a trigger, truncate, or create temp tables,
--                   so the append-only protection of signed records cannot be undone by it.
--
-- Run it as a superuser (the POSTGRES_USER of the db container) against the application
-- database. It is idempotent: safe to repeat, and to re-run after adding a table.
--
--   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f db_roles.sql
--
-- Passwords are never part of this file. Set them once, interactively:
--   \password medicore_owner
--   \password medicore_app
-- or pass them for a single run (URL-safe, e.g. `openssl rand -hex 24`):
--   psql ... -v owner_password="$OWNER_PW" -v app_password="$APP_PW" -f db_roles.sql
--
-- Convention: a table that must be append-only gets its own REVOKE in the migration that
-- creates it (see the audit and signed-record tables below); new tables otherwise inherit full
-- DML for medicore_app through the default privileges.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE medicore_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'medicore_owner') \gexec
SELECT 'CREATE ROLE medicore_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'medicore_app') \gexec
ALTER ROLE medicore_owner NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE medicore_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

\if :{?owner_password}
  SELECT format('ALTER ROLE medicore_owner PASSWORD %L', :'owner_password') \gexec
\endif
\if :{?app_password}
  SELECT format('ALTER ROLE medicore_app PASSWORD %L', :'app_password') \gexec
\endif

BEGIN;

-- The trigram index of the diagnosis search. Created here by the superuser so the owner role
-- never needs the privilege (the migrations only say IF NOT EXISTS).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO medicore_owner', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO medicore_app', current_database()) \gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO medicore_owner;
GRANT USAGE ON SCHEMA public TO medicore_app;

-- Hand over what the bootstrap superuser created. Extension members are skipped: they stay
-- with the extension, and a superuser cannot be reassigned wholesale (REASSIGN OWNED fails).
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.oid::regclass AS obj, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
       AND c.relowner <> 'medicore_owner'::regrole
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid
                          AND d.deptype IN ('e', 'a', 'i'))
  LOOP
    EXECUTE format('ALTER %s %s OWNER TO medicore_owner',
      CASE r.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW'
                     WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE'
                     ELSE 'TABLE' END, r.obj);
  END LOOP;
  FOR r IN
    SELECT p.oid::regprocedure AS obj
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.proowner <> 'medicore_owner'::regrole
       AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                          AND d.deptype = 'e')
  LOOP
    EXECUTE format('ALTER ROUTINE %s OWNER TO medicore_owner', r.obj);
  END LOOP;
END $$;

SET ROLE medicore_owner;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM medicore_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO medicore_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO medicore_app;

-- Per-table hardening. On a brand-new database the tables do not exist yet (the roles are
-- needed first so the backend can migrate): the statements are skipped with a NOTICE and the
-- script is simply run again after that first migration.
DO $$
DECLARE
  hardening text[][] := ARRAY[
    -- Signed records never change or disappear. UPDATE on one column is only what Postgres
    -- demands for SELECT ... FOR UPDATE / FOR NO KEY UPDATE, which the row locks rely on; the
    -- append-only trigger still refuses any actual UPDATE.
    ['medical_records', 'REVOKE UPDATE, DELETE ON medical_records FROM medicore_app'],
    ['medical_records', 'GRANT UPDATE (id) ON medical_records TO medicore_app'],
    -- Prescriptions close once, but are never deleted.
    ['prescriptions', 'REVOKE DELETE ON prescriptions FROM medicore_app'],
    -- Audit trails are written and read, never edited.
    ['audit_logs', 'REVOKE UPDATE, DELETE ON audit_logs FROM medicore_app'],
    ['platform_audit_logs', 'REVOKE UPDATE, DELETE ON platform_audit_logs FROM medicore_app'],
    -- The schema version moves only through migrations.
    ['alembic_version', 'REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM medicore_app']
  ];
  i int;
BEGIN
  FOR i IN 1 .. array_length(hardening, 1) LOOP
    IF to_regclass('public.' || hardening[i][1]) IS NULL THEN
      RAISE NOTICE 'skipped (table not created yet): %', hardening[i][2];
    ELSE
      EXECUTE hardening[i][2];
    END IF;
  END LOOP;
END $$;

ALTER DEFAULT PRIVILEGES FOR ROLE medicore_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO medicore_app;
ALTER DEFAULT PRIVILEGES FOR ROLE medicore_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO medicore_app;

RESET ROLE;

COMMIT;
