-- ブログ別の投稿済み（trn_dmm_items は作品マスタのまま）
create table if not exists public.trn_dmm_item_blog_post_status (
  id uuid not null default gen_random_uuid (),
  dmm_item_id uuid not null,
  blog_key text not null,
  is_posted boolean not null default false,
  posted_at timestamptz null,
  external_ref text null,
  created_at timestamptz null default now(),
  updated_at timestamptz null default now(),
  constraint trn_dmm_item_blog_post_status_pkey primary key (id),
  constraint trn_dmm_item_blog_post_status_item_blog_key unique (dmm_item_id, blog_key),
  constraint trn_dmm_item_blog_post_status_dmm_item_id_fkey
    foreign key (dmm_item_id) references public.trn_dmm_items (id) on delete cascade
) tablespace pg_default;

create index if not exists idx_dmm_item_blog_post_status_blog_posted
  on public.trn_dmm_item_blog_post_status (blog_key, is_posted);

create index if not exists idx_dmm_item_blog_post_status_item
  on public.trn_dmm_item_blog_post_status (dmm_item_id);
