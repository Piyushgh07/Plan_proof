#!/usr/bin/env bash
set -euo pipefail

psql \
  --username "$POSTGRES_USER" \
  --dbname postgres \
  --set ON_ERROR_STOP=1 \
  --set app_user="$APP_DB_USER" \
  --set app_password="$APP_DB_PASSWORD" \
  --set target_reader="$TARGET_READER_USER" \
  --set target_reader_password="$TARGET_READER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', 'app_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'app_db')
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L',
    :'target_reader',
    :'target_reader_password'
)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'target_reader')
\gexec

\connect target_db
REVOKE CONNECT ON DATABASE target_db FROM PUBLIC;
GRANT CONNECT ON DATABASE target_db TO target_admin, :"target_reader";
GRANT USAGE ON SCHEMA public TO :"target_reader";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"target_reader";
ALTER DEFAULT PRIVILEGES FOR ROLE target_admin IN SCHEMA public
    GRANT SELECT ON TABLES TO :"target_reader";
SQL
