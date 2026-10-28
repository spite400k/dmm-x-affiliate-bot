-- FANZA ジャンルハブ用（docs/livedoor-internal-links-design.md Phase 2）
-- 既存行は NULL のまま。アプリは NULL ならハブ非表示／floor 既定ラベルにフォールバック。

alter table public.mst_blog_accounts
  add column if not exists public_base_url text null;

alter table public.mst_blog_accounts
  add column if not exists genre_label text null;

alter table public.mst_blog_accounts
  add column if not exists hub_group text null;

comment on column public.mst_blog_accounts.public_base_url is
  'ブログ公開 TOP URL（例: https://blog.livedoor.jp/xxx/）。ジャンルハブと AtomPub URL フォールバック用';

comment on column public.mst_blog_accounts.genre_label is
  'ハブ表示名（例: コミック / 同人誌 / AV / 素人）。空時は floor 既定';

comment on column public.mst_blog_accounts.hub_group is
  '同一ハブに載せるグループ（例: fanza）。空ならハブ対象外';

-- 例（blog_id / URL は実環境に合わせて書き換える）:
-- update public.mst_blog_accounts
--   set public_base_url = 'https://blog.livedoor.jp/example-comic/',
--       genre_label = 'コミック',
--       hub_group = 'fanza'
-- where platform = 'livedoor' and account_id = '2' and floor = 'comic';
