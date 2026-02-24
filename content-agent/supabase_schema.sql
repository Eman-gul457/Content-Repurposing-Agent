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

create table if not exists media_assets (
  id bigserial primary key,
  user_id text not null,
  post_id bigint not null references generated_posts(id) on delete cascade,
  platform text not null default 'linkedin',
  file_name text not null,
  mime_type text not null,
  file_size bigint default 0,
  storage_path text not null,
  file_url text default '',
  platform_asset_id text default '',
  upload_status text default 'uploaded',
  last_error text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_media_assets_user on media_assets(user_id);
create index if not exists idx_media_assets_post on media_assets(post_id);

create table if not exists agent_runs (
  id bigserial primary key,
  user_id text not null,
  business_name text default '',
  niche text default '',
  audience text default '',
  tone text default '',
  region text default '',
  platforms_csv text default '',
  language_pref text default 'english_urdu',
  source_content text default '',
  status text default 'running',
  error_text text default '',
  created_at timestamptz default now(),
  completed_at timestamptz null
);

create index if not exists idx_agent_runs_user on agent_runs(user_id);
create index if not exists idx_agent_runs_status on agent_runs(status);

create table if not exists research_items (
  id bigserial primary key,
  user_id text not null,
  run_id bigint null references agent_runs(id) on delete set null,
  source text not null,
  title text not null,
  url text default '',
  snippet text default '',
  published_at timestamptz null,
  created_at timestamptz default now()
);

create index if not exists idx_research_items_user on research_items(user_id);
create index if not exists idx_research_items_run on research_items(run_id);

create table if not exists content_plans (
  id bigserial primary key,
  user_id text not null,
  run_id bigint null references agent_runs(id) on delete set null,
  platform text not null,
  language_pref text default 'english_urdu',
  planned_for timestamptz null,
  status text default 'planned',
  theme text default '',
  post_angle text default '',
  image_prompt text default '',
  image_url text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_content_plans_user on content_plans(user_id);
create index if not exists idx_content_plans_run on content_plans(run_id);
create index if not exists idx_content_plans_platform on content_plans(platform);

create table if not exists approval_requests (
  id bigserial primary key,
  user_id text not null,
  post_id bigint not null references generated_posts(id) on delete cascade,
  status text default 'pending',
  requested_at timestamptz default now(),
  resolved_at timestamptz null,
  resolution_note text default ''
);

create index if not exists idx_approval_requests_user on approval_requests(user_id);
create index if not exists idx_approval_requests_post on approval_requests(post_id);

create table if not exists publish_jobs (
  id bigserial primary key,
  user_id text not null,
  post_id bigint not null references generated_posts(id) on delete cascade,
  platform text not null,
  status text default 'pending',
  scheduled_at timestamptz null,
  attempted_at timestamptz null,
  completed_at timestamptz null,
  error_message text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_publish_jobs_user on publish_jobs(user_id);
create index if not exists idx_publish_jobs_post on publish_jobs(post_id);
create index if not exists idx_publish_jobs_status on publish_jobs(status);
