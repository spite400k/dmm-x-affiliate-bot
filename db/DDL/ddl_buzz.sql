create table trn_articles (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  content text not null,
  created_at timestamp with time zone default now()
);


create table trn_posts (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  type text check (type in ('謎', '議論', '解説')),
  article_id uuid references trn_articles(id) on delete set null,
  status text default 'draft' check (status in ('draft', 'scheduled', 'posted')),
  scheduled_at timestamp with time zone,
  posted_at timestamp with time zone,
  tweet_id text,
  created_at timestamp with time zone default now()
);

create table trn_post_replies (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references trn_posts(id) on delete cascade,
  content text not null,
  scheduled_at timestamp with time zone not null,
  posted_at timestamp with time zone,
  created_at timestamp with time zone default now()
); 


create table trn_post_logs (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references trn_posts(id) on delete cascade,
  impressions int default 0,
  likes int default 0,
  replies int default 0,
  created_at timestamp with time zone default now()
);

create table trn_post_images (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references trn_posts(id) on delete cascade,
  image_url text,
  created_at timestamp with time zone default now()
);