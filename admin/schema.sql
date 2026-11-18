-- Scraping Hub accounts. Run once in Supabase (SQL Editor) before the first deploy.
create table if not exists hub_accounts (
  email        text primary key,
  name         text not null,
  salt         text not null,          -- PBKDF2-SHA256, 200,000 rounds; never the password
  hash         text not null,
  status       text not null default 'pending' check (status in ('pending', 'approved')),
  requested_at timestamptz not null default now(),
  decided_by   text,
  decided_at   timestamptz
);

-- Only the panel's server (DATABASE_URL) reads this table; nothing reaches it from a browser.
alter table hub_accounts enable row level security;
