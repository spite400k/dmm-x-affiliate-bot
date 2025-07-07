create table public.trn_posts (
  id uuid primary key default gen_random_uuid(),
  comment text,
  image_urls text[],         -- 画像URL（最大4枚ずつ投稿される）
  affiliate_url text,
  posted boolean default false,
  created_at timestamp with time zone default now()
);
