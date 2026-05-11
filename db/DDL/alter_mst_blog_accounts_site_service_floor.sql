-- 既存の mst_blog_accounts に site / service / floor を追加するマイグレーション
-- （create table 済みの環境向け。新規は ddl_mst_blog_accounts.sql に含まれる）

alter table public.mst_blog_accounts
  add column if not exists site text null;

alter table public.mst_blog_accounts
  add column if not exists service text null;

alter table public.mst_blog_accounts
  add column if not exists floor text null;
