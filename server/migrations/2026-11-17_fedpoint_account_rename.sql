-- The EUNA BONFIRE (ridemetro) account "Fedpints" is now "FedPoint": its key
-- went from 'fedpints' to 'fedpoint' (app/scrapers/ridemetro/accounts.py), so
-- runs saved under the old key are renamed to match. Only the account fields
-- change; each run's folder path still names the real folder on disk and is
-- left as it is.
--
--   psql "$DATABASE_URL" -f server/migrations/2026-11-17_fedpoint_account_rename.sql
--
-- Idempotent: safe to run more than once.

UPDATE ridemetro_runs SET account = 'fedpoint' WHERE account = 'fedpints';

UPDATE run_state
SET data = jsonb_set(jsonb_set(data, '{account}', '"fedpoint"'), '{account_label}', '"FedPoint"')
WHERE data->>'account' = 'fedpints';
