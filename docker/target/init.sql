-- Enable PostgreSQL query statistics collection.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Application role.
CREATE USER app_user WITH PASSWORD 'app_password';

-- Application metadata database.
CREATE DATABASE app_db OWNER app_user;

-- Prevent the application role from connecting to the target database.
REVOKE CONNECT ON DATABASE target_db FROM PUBLIC;

-- Explicitly allow the target administrator to connect.
GRANT CONNECT ON DATABASE target_db TO target_admin;