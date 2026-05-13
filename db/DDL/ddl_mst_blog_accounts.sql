-- アカウント別・プラットフォーム別のブログ接続（FC2 XML-RPC / ライブドア AtomPub 等）
-- application: db/blog_repository.py（BLOG_ACCOUNT_MASTER_TABLE でテーブル名変更可）
--
-- platform = 'livedoor' のとき:
--   blog_id … AtomPub のブログ名（POST は …/atompub/{blog_id}/article。例: blog.livedoor.jp/staff/ なら staff）
--   username … livedoor ID（従来の LIVEDOOR_ID）
--   api_password … AtomPub 用 API キー（従来の LIVEDOOR_ATOMPUB_PASSWORD）
--   blog_key … 任意。備考用（人間可読なブログ名など）。投稿済みキーはアプリが livedoor:{blog_id} を使う
--   blog_memo … blog_key の別名としても可（どちらかに備考を入れればログに出る）
--   xmlrpc_url … ライブドアでは未使用（NULL でよい）
--   site … 任意。dmm / fanza または DMM.com（ポータルリンク・未投稿キュー参照。ライブドアは行ごとに解決）
--   service, floor … 任意。ライブドアは複数行のとき各行の組み合わせでキュー参照（無いときのみ config targets）
--
-- platform = 'fc2' のとき:
--   xmlrpc_url … 未指定なら http://blog.fc2.com/xmlrpc.php（アプリ側デフォルト）
--   site, service, floor … 任意。config の targets が空のとき main_fc2_blog の 1 件キュー指定に使用

drop table  public.mst_blog_accounts;
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
  site text null,
  service text null,
  floor text null,
  created_at timestamptz null default now(),
  updated_at timestamptz null default now(),
  constraint mst_blog_accounts_pkey primary key (id),
  constraint mst_blog_accounts_account_platform_key unique (account_id, platform,site,service,floor)
) tablespace pg_default;

create index if not exists idx_mst_blog_accounts_account
  on public.mst_blog_accounts (account_id);

create index if not exists idx_mst_blog_accounts_platform_enabled
  on public.mst_blog_accounts (platform, enabled);




INSERT INTO "public"."mst_blog_accounts" ("account_id", "platform", "enabled", "blog_id", "username", "api_password", "blog_key", "xmlrpc_url","site","service","floor") VALUES ('1', 'livedoor', true, 'spite400k', 'spite400k', 'ck10ZFkiPs', 'mangamanga:マンガマンガ', null,'DMM.com','ebook','comic');

INSERT INTO "public"."mst_blog_accounts" ("id", "account_id", "platform", "enabled", "blog_id", "username", "api_password", "blog_key", "xmlrpc_url","site","service","floor", "created_at", "updated_at") VALUES ('34ea68f0-cf4a-45bb-bb65-f5ce4489ea9d', '1', 'livedoor', true, 'spite400k-hp7qpmu3', 'spite400k', 'ck10ZFkiPs', 'photoselect:写真集セレクト', null,'DMM.com','ebook','photo', '2026-05-10 21:34:28.585379+00', '2026-05-10 21:34:28.585379+00');