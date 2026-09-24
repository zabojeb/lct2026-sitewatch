\set ON_ERROR_STOP on

-- Supply both passwords through psql -v; never store them in this file.
SELECT format('CREATE ROLE sitewatch_schedule_migrator LOGIN PASSWORD %L', :'migration_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sitewatch_schedule_migrator') \gexec
SELECT format('ALTER ROLE sitewatch_schedule_migrator PASSWORD %L', :'migration_password') \gexec
SELECT format('CREATE ROLE sitewatch_schedule LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sitewatch_schedule') \gexec
SELECT format('ALTER ROLE sitewatch_schedule PASSWORD %L', :'runtime_password') \gexec
SELECT 'CREATE DATABASE sitewatch_schedule OWNER sitewatch_schedule_migrator'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'sitewatch_schedule') \gexec
REVOKE ALL ON DATABASE sitewatch_schedule FROM PUBLIC;
GRANT CONNECT ON DATABASE sitewatch_schedule TO sitewatch_schedule;

\connect sitewatch_schedule
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sitewatch_schedule;
ALTER DEFAULT PRIVILEGES FOR ROLE sitewatch_schedule_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO sitewatch_schedule;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sitewatch_schedule;
