create table public.mst_genre (
  id integer primary key,
  name text not null,
  created_at timestamp with time zone default now()
);
