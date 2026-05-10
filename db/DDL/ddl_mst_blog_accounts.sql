-- アカウント別・プラットフォーム別のブログ接続（FC2 XML-RPC / ライブドア AtomPub 等）
-- application: db/blog_repository.py（BLOG_ACCOUNT_MASTER_TABLE でテーブル名変更可）
--
-- platform = 'livedoor' のとき:
--   blog_id … AtomPub のパス識別子（例: https://livedoor.blogcms.jp/atompub/spite400k-dkg6rbhs なら spite400k-dkg6rbhs）
--   username … livedoor ID（従来の LIVEDOOR_ID）
--   api_password … AtomPub 用 API キー（従来の LIVEDOOR_ATOMPUB_PASSWORD）
--   blog_key … 任意。未指定なら livedoor:{blog_id}（trn_dmm_item_blog_post_status と一致させる）
--   xmlrpc_url … ライブドアでは未使用（NULL でよい）
--
-- platform = 'fc2' のとき:
--   xmlrpc_url … 未指定なら http://blog.fc2.com/xmlrpc.php（アプリ側デフォルト）

create table if not exists public.mst_blog_accounts (
  id uuid not null default gen_random_uuid (),
  account_id text not null,
  platform text not null,
  enabled boolean not null default false,
  blog_id text not null,
  username text not null,
  api_password text not null,
  blog_key text null,
  xmlrpc_url text null,
  created_at timestamptz null default now(),
  updated_at timestamptz null default now(),
  constraint mst_blog_accounts_pkey primary key (id),
  constraint mst_blog_accounts_account_platform_key unique (account_id, platform)
) tablespace pg_default;

create index if not exists idx_mst_blog_accounts_account
  on public.mst_blog_accounts (account_id);

create index if not exists idx_mst_blog_accounts_platform_enabled
  on public.mst_blog_accounts (platform, enabled);
