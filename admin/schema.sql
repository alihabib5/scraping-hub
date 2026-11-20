-- Scraping Hub accounts. Run once in Supabase (SQL Editor) before the first deploy.
-- (A database made from an older copy of this file: run migrations/001_sessions.sql instead.)
create table if not exists hub_accounts (
  email        text primary key,
  name         text not null,
  salt         text not null,          -- PBKDF2-SHA256, 200,000 rounds; never the password
  hash         text not null,
  status       text not null default 'pending' check (status in ('pending', 'approved')),
  requested_at timestamptz not null default now(),
  requested_ip text,
  decided_by   text,
  decided_at   timestamptz
);

-- One row per sign-in in the Windows app; the dashboard shows each user's latest.
create table if not exists hub_sessions (
  id           uuid primary key default gen_random_uuid(),
  email        text not null references hub_accounts (email) on delete cascade,
  ip           text,
  started_at   timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),  -- the app checks in every few minutes
  ended_at     timestamptz                          -- sign-out or app close; null while open
);
create index if not exists hub_sessions_email_started on hub_sessions (email, started_at desc);

-- Only the panel's server (DATABASE_URL) reads these tables; nothing reaches them from a browser.
alter table hub_accounts enable row level security;
alter table hub_sessions enable row level security;
