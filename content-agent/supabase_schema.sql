-- Run this in Supabase SQL Editor before starting backend.

create table if not exists social_accounts (
  id bigserial primary key,
  user_id text not null,
  platform text not null,
  account_id text not null,
  account_name text default '',
  access_token_enc text not null,
  refresh_token_enc text default '',
  expires_at timestamptz null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create unique index if not exists uq_user_platform on social_accounts(user_id, platform);
create index if not exists idx_social_accounts_user on social_accounts(user_id);

create table if not exists generated_posts (
  id bigserial primary key,
  user_id text not null,
  platform text not null,
  input_content text not null,
  generated_text text not null,
  edited_text text default '',
  status text default 'draft',
  scheduled_at timestamptz null,
  posted_at timestamptz null,
  external_post_id text default '',
  last_error text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_generated_posts_user on generated_posts(user_id);
create index if not exists idx_generated_posts_status on generated_posts(status);

create table if not exists oauth_states (
  id bigserial primary key,
  user_id text not null,
  provider text not null,
  state_token text not null unique,
  created_at timestamptz default now()
);

create index if not exists idx_oauth_states_user on oauth_states(user_id);