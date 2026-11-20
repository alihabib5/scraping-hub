-- Run once in Supabase (SQL Editor) on a database made from the first schema.sql.
-- Adds what the dashboard shows: the IP a sign-up came from, and each sign-in session.
-- Safe to run twice.
alter table hub_accounts add column if not exists requested_ip text;

create table if not exists hub_sessions (
  id           uuid primary key default gen_random_uuid(),
  email        text not null references hub_accounts (email) on delete cascade,
  ip           text,
  started_at   timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),  -- the app checks in every few minutes
  ended_at     timestamptz                          -- sign-out or app close; null while open
);
create index if not exists hub_sessions_email_started on hub_sessions (email, started_at desc);

alter table hub_sessions enable row level security;
