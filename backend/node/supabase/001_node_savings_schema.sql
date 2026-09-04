-- Run this migration in the Supabase SQL editor before starting the Node webhook service.
create table if not exists public.node_transactions (
  id uuid primary key default gen_random_uuid(),
  transaction_id text not null unique,
  user_id text not null,
  type text not null check (type in ('debit', 'payout')),
  amount numeric(12,2) not null check (amount >= 0),
  source text not null,
  timestamp timestamptz not null,
  status text not null default 'pending' check (status in ('pending', 'processed', 'failed')),
  is_processed boolean not null default false,
  raw_payload jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.node_savings_stashes (
  id uuid primary key default gen_random_uuid(),
  user_id text not null unique,
  current_balance numeric(12,2) not null default 0 check (current_balance >= 0),
  pending_contributions numeric(12,2) not null default 0 check (pending_contributions >= 0),
  last_sweep_date timestamptz,
  sweep_history jsonb not null default '[]'::jsonb,
  minimum_threshold numeric(12,2) not null default 100,
  mandate_cap numeric(12,2) not null default 1000,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.node_income_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id text not null unique,
  rolling30_day_payouts jsonb not null default '[]'::jsonb,
  current_rolling_average numeric(12,2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists node_transactions_user_processed_idx
  on public.node_transactions (user_id, is_processed);
create index if not exists node_transactions_user_type_time_idx
  on public.node_transactions (user_id, type, timestamp desc);
