-- ジャンルハブ用（docs/livedoor-internal-links-design.md）
-- 既存行は NULL のまま。アプリは NULL ならハブ非表示／floor 既定ラベルにフォールバック。
-- hub_group 例: fanza / dmm（site と同名にすると解決が簡単）

alter table public.mst_blog_accounts
  add column if not exists public_base_url text null;

alter table public.mst_blog_accounts
  add column if not exists genre_label text null;

alter table public.mst_blog_accounts
  add column if not exists hub_group text null;

comment on column public.mst_blog_accounts.public_base_url is
  'ブログ公開 TOP URL（例: https://blog.livedoor.jp/xxx/）。ジャンルハブと AtomPub URL フォールバック用';

comment on column public.mst_blog_accounts.genre_label is
  'ハブ表示名（例: コミック / 写真集 / 同人誌 / AV / 素人）。空時は floor 既定';

comment on column public.mst_blog_accounts.hub_group is
  '同一ハブに載せるグループ（例: fanza / dmm）。空ならハブ対象外';

-- ---------------------------------------------------------------------------
-- 値入れ（blog_id から TOP URL を組み立てる。カスタムドメイン時は手で書き換え）
-- ---------------------------------------------------------------------------

-- DMM（account_id=1）
update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = 'コミック',
  hub_group = 'dmm'
where platform = 'livedoor'
  and account_id = '1'
  and floor = 'comic';

update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = '写真集',
  hub_group = 'dmm'
where platform = 'livedoor'
  and account_id = '1'
  and floor = 'photo';

-- FANZA（account_id=2）
update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = 'AV',
  hub_group = 'fanza'
where platform = 'livedoor'
  and account_id = '2'
  and floor = 'videoa';

update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = 'コミック',
  hub_group = 'fanza'
where platform = 'livedoor'
  and account_id = '2'
  and floor = 'comic';

update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = '同人誌',
  hub_group = 'fanza'
where platform = 'livedoor'
  and account_id = '2'
  and floor = 'digital_doujin';

update public.mst_blog_accounts
set
  public_base_url = 'https://blog.livedoor.jp/' || blog_id || '/',
  genre_label = '素人',
  hub_group = 'fanza'
where platform = 'livedoor'
  and account_id = '2'
  and floor = 'videoc';
