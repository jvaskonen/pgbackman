--
-- PgBackMan database - Upgrade from 4:1_3_0 to 5:1_3_1
--
-- Copyright (c) 2023 James Miller, Turnitin, LLC.
--
-- This file is part of a PgBackMan fork
-- https://github.com/jvaskonen/pgbackman
--

BEGIN;

--Update function update_backup_server_config to no longer take bin dir parameters since binary directories are now
--set with their own functions. Also adding the ability to set some other parameters that are not currently exposed

DROP FUNCTION update_backup_server_config(INTEGER,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT);

CREATE OR REPLACE FUNCTION update_backup_server_config(INTEGER,TEXT,TEXT,TEXT,TEXT,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  backup_server_id_      ALIAS FOR $1;
  pgbackman_dump_        ALIAS FOR $2;
  pgbackman_restore_     ALIAS FOR $3;
  admin_user_            ALIAS FOR $4;
  domain_                ALIAS FOR $5;
  root_backup_partition_ ALIAS FOR $6;

  server_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*) FROM backup_server WHERE server_id = backup_server_id_ INTO server_cnt;

   IF server_cnt != 0 THEN

     EXECUTE 'UPDATE backup_server_config SET value = $2 WHERE server_id = $1 AND parameter = ''pgbackman_dump'''
     USING backup_server_id_,
           pgbackman_dump_;

     EXECUTE 'UPDATE backup_server_config SET value = $2 WHERE server_id = $1 AND parameter = ''pgbackman_restore'''
     USING backup_server_id_,
           pgbackman_restore_;

     EXECUTE 'UPDATE backup_server_config SET value = $2 WHERE server_id = $1 AND parameter = ''admin_user'''
     USING backup_server_id_,
           admin_user_;

     EXECUTE 'UPDATE backup_server_config SET value = $2 WHERE server_id = $1 AND parameter = ''domain'''
     USING backup_server_id_,
           domain_;

     EXECUTE 'UPDATE backup_server_config SET value = $2 WHERE server_id = $1 AND parameter = ''root_backup_partition'''
     USING backup_server_id_,
           root_backup_partition_;

    ELSE
      RAISE EXCEPTION 'Backup server % does not exist',backup_server_id_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION update_backup_server_config(INTEGER,TEXT,TEXT,TEXT,TEXT,TEXT) OWNER TO pgbackman_role_rw;

-- -------------------------------------------------------------------------------------------------------------
-- Function: apply_new_backup_server_default()
-- When a new backup server default value is insert, update all existing server configurations with that default
-- -------------------------------------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION apply_new_backup_server_default() RETURNS TRIGGER
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 BEGIN

  EXECUTE 'INSERT INTO backup_server_config (server_id,parameter,value,description)
           SELECT backup_server.server_id, parameter, value, description
           FROM backup_server_default_config, backup_server
           WHERE backup_server_default_config.parameter = $1
                 AND NOT EXISTS( SELECT 1
                                 FROM backup_server_config
                                 WHERE backup_server_config.parameter = $1
                                 AND backup_server_config.server_id = backup_server.server_id
                               )
          '
  USING NEW.parameter;

  RETURN NULL;

END;
$$;

ALTER FUNCTION apply_new_backup_server_default() OWNER TO pgbackman_role_rw;

CREATE TRIGGER apply_new_backup_server_default AFTER INSERT
    ON backup_server_default_config FOR EACH ROW
    EXECUTE PROCEDURE apply_new_backup_server_default();

-- Function register_backup_server_pg_bin_dir
-- Adds the postgres binary directory for a given server and version of postgres

CREATE OR REPLACE FUNCTION register_backup_server_pg_bin_dir(INTEGER,TEXT,TEXT,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  backup_server_id_      ALIAS FOR $1;
  postgres_version_      ALIAS FOR $2;
  bin_dir_               ALIAS FOR $3;
  description_           ALIAS FOR $4;

  server_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server
       WHERE server_id = backup_server_id_
       INTO server_cnt;

   IF server_cnt != 0 THEN

     EXECUTE 'INSERT INTO backup_server_config (server_id,parameter,value,description)
              VALUES ( $1, ''pgsql_bin_'' || $2, $3, $4)'
     USING backup_server_id_,
           bin_dir_,
           postgres_version_,
           description_;

    ELSE
      RAISE EXCEPTION 'Backup server % does not exist',backup_server_id_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION register_backup_server_pg_bin_dir(INTEGER,TEXT,TEXT,TEXT) OWNER TO pgbackman_role_rw;

-- Function register_backup_server_default_pg_bin_dir
-- Sets the default postgres binary directory for a given version of postgres

CREATE OR REPLACE FUNCTION register_backup_server_default_pg_bin_dir(TEXT,TEXT,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  postgres_version_      ALIAS FOR $1;
  bin_dir_               ALIAS FOR $2;
  description_           ALIAS FOR $3;

  config_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server_default_config
       WHERE parameter = 'pgsql_bin_' || postgres_version_
       INTO config_cnt;

   IF config_cnt = 0 THEN

     EXECUTE 'INSERT INTO backup_server_default_config(parameter,value,description)
              VALUES (''pgsql_bin_'' || $2, $1, $3)'
     USING bin_dir_,
           postgres_version_,
           description_;

    ELSE
      RAISE EXCEPTION 'A default binary directory for postgres % has already been configured', postgres_version_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION register_backup_server_default_pg_bin_dir(TEXT,TEXT,TEXT) OWNER TO pgbackman_role_rw;

-- Function update_backup_server_pg_bin_dir
-- Sets the postgres binary directory for a given server and version of postgres

CREATE OR REPLACE FUNCTION update_backup_server_pg_bin_dir(INTEGER,TEXT,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  backup_server_id_      ALIAS FOR $1;
  postgres_version_      ALIAS FOR $2;
  bin_dir_               ALIAS FOR $3;

  server_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server
            JOIN backup_server_config ON backup_server_config.server_id = backup_server.server_id
       WHERE backup_server.server_id = backup_server_id_
             AND parameter = 'pgsql_bin_' || postgres_version_
       INTO server_cnt;

   IF server_cnt != 0 THEN

     EXECUTE 'UPDATE backup_server_config
              SET value = $2
              WHERE server_id = $1 AND parameter = ''pgsql_bin_'' || $3'
     USING backup_server_id_,
           bin_dir_,
           postgres_version_;

    ELSE
      RAISE EXCEPTION 'Backup server % does not exist or does have postgres % configured',backup_server_id_, postgres_version_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION update_backup_server_pg_bin_dir(INTEGER,TEXT,TEXT) OWNER TO pgbackman_role_rw;

-- Function update_backup_server_default_pg_bin_dir
-- Sets the default postgres binary directory for a given version of postgres

CREATE OR REPLACE FUNCTION update_backup_server_default_pg_bin_dir(TEXT,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  postgres_version_      ALIAS FOR $1;
  bin_dir_               ALIAS FOR $2;

  server_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server_default_config
       WHERE parameter = 'pgsql_bin_' || postgres_version_
       INTO server_cnt;

   IF server_cnt != 0 THEN

     EXECUTE 'UPDATE backup_server_default_config
              SET value = $1 WHERE parameter = ''pgsql_bin_'' || $2'
     USING bin_dir_,
           postgres_version_;

    ELSE
      RAISE EXCEPTION 'A default binary directory for postgres % has not been configured', postgres_version_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION update_backup_server_default_pg_bin_dir(TEXT,TEXT) OWNER TO pgbackman_role_rw;

-- Function delete_backup_server_pg_bin_dir
-- Drop support for a given version of postgres from the specified backup server

CREATE OR REPLACE FUNCTION delete_backup_server_pg_bin_dir(INTEGER,TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  backup_server_id_      ALIAS FOR $1;
  postgres_version_      ALIAS FOR $2;

  server_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server_config
       WHERE server_id = backup_server_id_
             AND parameter = 'pgsql_bin_' || postgres_version_
       INTO server_cnt;

   IF server_cnt != 0 THEN

     EXECUTE 'DELETE FROM backup_server_config
              WHERE server_id = $1 AND parameter = ''pgsql_bin_'' || $2'
     USING backup_server_id_,
           postgres_version_;

    ELSE
      RAISE EXCEPTION 'Server % does not exist or postgres version % has not been configured', backup_server_id_, postgres_version_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION delete_backup_server_pg_bin_dir(INTEGER,TEXT) OWNER TO pgbackman_role_rw;

-- Function delete_backup_server_default_pg_bin_dir
-- Drop support for a given version from the backup server defaults

CREATE OR REPLACE FUNCTION delete_backup_server_default_pg_bin_dir(TEXT) RETURNS VOID
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path = public, pg_temp
 AS $$
 DECLARE
  postgres_version_      ALIAS FOR $1;

  config_cnt INTEGER;
  v_msg     TEXT;
  v_detail  TEXT;
  v_context TEXT;
 BEGIN

   SELECT count(*)
       FROM backup_server_default_config
       WHERE parameter = 'pgsql_bin_' || postgres_version_
       INTO config_cnt;

   IF config_cnt != 0 THEN

     EXECUTE 'DELETE FROM backup_server_default_config
              WHERE parameter = ''pgsql_bin_'' || $1'
     USING postgres_version_;

    ELSE
      RAISE EXCEPTION 'A default binary directory for postgres % has not been configured', postgres_version_;
    END IF;

   EXCEPTION WHEN others THEN
        GET STACKED DIAGNOSTICS
            v_msg     = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_context = PG_EXCEPTION_CONTEXT;
        RAISE EXCEPTION E'\n----------------------------------------------\nEXCEPTION:\n----------------------------------------------\nMESSAGE: % \nDETAIL : % \n----------------------------------------------\n', v_msg, v_detail;
  END;
$$;

ALTER FUNCTION delete_backup_server_default_pg_bin_dir(TEXT) OWNER TO pgbackman_role_rw;

-- Add default binary directories for more recent versions of postgres

INSERT INTO backup_server_default_config (parameter,value,description)
    SELECT *
    FROM ( VALUES ('pgsql_bin_11','/usr/pgsql-11/bin','postgreSQL 11 bin directory'),
                  ('pgsql_bin_12','/usr/pgsql-12/bin','postgreSQL 12 bin directory'),
                  ('pgsql_bin_13','/usr/pgsql-13/bin','postgreSQL 13 bin directory'),
                  ('pgsql_bin_14','/usr/pgsql-14/bin','postgreSQL 14 bin directory'),
                  ('pgsql_bin_15','/usr/pgsql-14/bin','postgreSQL 14 bin directory'),
                  ('pgsql_bin_16','/usr/pgsql-15/bin','postgreSQL 15 bin directory')
         ) AS new_defaults(parameter,value,description)
    WHERE NOT EXISTS ( SELECT 1
                       FROM backup_server_default_config dc
                       WHERE dc.parameter = new_defaults.parameter
                     );

-- Update pgbackman_version with information about version 5:1_3_1

INSERT INTO pgbackman_version (version,tag) VALUES ('5','v_1_3_1');

COMMIT;
