# ライブドアブログ内部リンク設計

合意方針（2026-10-28）:

1. **同ブログ（同ジャンル）内**の関連記事 2〜3 件を記事末に出す（本命）
2. **FANZA ジャンル別ブログ**は、記事本文での横断リンクはしない。共通フッターで **各ブログ TOP** へ軽く導線
3. コミック↔同人、AV↔素人は「近い」が、v1 では記事単位の相互リンクは出さない（TOP 導線のみ）

対象: `main_livedoor_atompub.py` / `livedoor_blog/post.py`（Seesaa・FC2 はスコープ外。HTML ビルダ共通化後に横展開可）

---

## 1. 現状とギャップ

| 項目 | 現状 | ギャップ |
|------|------|----------|
| 記事本文 | レビュー → 画像 → CTA → プレミアム | 自ブログ内回遊なし |
| 投稿済み | `trn_dmm_item_blog_post_status`（`blog_key=livedoor:{blog_id}`） | `external_ref` 列はあるが未使用 |
| AtomPub | POST 成功後に応答を捨てている | 公開 URL を保存していない |
| ブログマスタ | `mst_blog_accounts`（blog_id / site / service / floor） | 公開 TOP URL・ジャンル表示名なし |

関連リンクは **公開記事 URL** が必須。URL 永続化が Phase 0。

---

## 2. 目標 UI（記事 HTML）

本文末尾の並び（既存⑤のあと）:

```
… ④ ポータル CTA
… ⑤ プレミアム宣伝（条件付き）
… ⑥ 関連記事（同ブログ・0〜3件。件数0ならセクションごと省略）
… ⑦ FANZA ジャンルハブ（site=fanza かつ設定があるときのみ）
… （popular 時の PR 注記は従来どおり article 末尾）
```

### ⑥ 関連記事（同ブログ）

- 見出し例: `あわせて読みたい`
- 件数: **最大 3**（環境変数で変更可、既定 3）
- 各行: 記事タイトルへの `<a href="{public_url}">`（nofollow は付けない。自サイト内リンク）
- サムネは v1 では出さない（本文肥大・外部画像依存を避ける）
- 候補が 0 件ならセクション非表示（新規ブログ初日など）

### ⑦ FANZA ジャンルハブ

- 見出し例: `ジャンルから探す`
- 表示: `コミック | 同人誌 | AV | 素人` のような **ブログ TOP へのテキストリンク**
- **現在記事のジャンル自身はリンクに含めない**（または現在地として強調のみ・href なし）
- 記事本文への他ジャンル個別記事リンクは **出さない**
- `site` が dmm のブログでは出さない（FANZA ジャンル分割の話のため）

---

## 3. データモデル

### 3.1 `trn_dmm_item_blog_post_status.external_ref`（既存列を利用）

投稿成功時に公開 URL を保存する。

推奨フォーマット（テキスト1本）:

```text
https://blog.livedoor.jp/{blog_id}/archives/{article_id}.html
```

カスタムドメイン時は AtomPub 応答の値をそのまま保存（推測で組み立てない）。

任意で将来拡張するなら JSON も可だが、v1 は **URL 文字列1本** で十分。

```text
# 将来案（採用しない）
{"url":"https://...","article_id":"123","edit_href":"https://livedoor.blogcms.jp/..."}
```

### 3.2 AtomPub 応答からの URL 抽出

POST 成功レスポンス（201）の Atom entry から次の優先順で取得:

1. `<link rel="alternate" type="text/html" href="...">`
2. `<content ... xml:base="...">` の xml:base
3. `<link rel="edit" href=".../article/{id}">` から article_id を取り、  
   `public_base_url` + `archives/{id}.html` で組み立て（フォールバック）

抽出失敗時:

- 投稿自体は成功扱い（現行どおり `is_posted` を立てる）
- `external_ref` は NULL のまま
- 関連候補から除外される（リンク切れを出さない）
- ログに warning

### 3.3 `mst_blog_accounts` 拡張（任意カラム）

DDL に nullable 列を追加（既存行は NULL 可）:

| 列 | 用途 |
|----|------|
| `public_base_url` | ブログ TOP。例 `https://blog.livedoor.jp/xxx/`。ハブリンクと URL フォールバック用 |
| `genre_label` | ハブ表示名。例 `コミック` / `同人誌` / `AV` / `素人` |
| `hub_group` | 同じハブに載せるグループキー。例 `fanza`。空ならハブ非表示 |

`floor` からの既定ラベル（`genre_label` 空時）:

| floor | 既定ラベル |
|-------|------------|
| `comic` | コミック |
| `digital_doujin` | 同人誌 |
| `videoa` | AV |
| `videoc` | 素人 |
| その他 | ハブに載せない（明示 `genre_label` があるときのみ） |

`hub_group` が同じ・`platform=livedoor`・`enabled=true`・`public_base_url` あり・（`genre_label` または上表の既定あり）の行をハブ候補とする。

---

## 4. 関連記事の選定ロジック

### 4.1 入力

- 現在の `blog_key`（例 `livedoor:foo`）
- 現在の `dmm_item_id`（除外用）
- 現在の `item_row`（類似スコア用）
- `limit`（既定 3）

### 4.2 候補プール

1. `trn_dmm_item_blog_post_status` から  
   `blog_key = 現在` AND `is_posted = true` AND `external_ref IS NOT NULL` AND `dmm_item_id <> 現在`  
   を直近 `posted_at` 降順で最大 N 件取得（N 既定 30。スコア用バッファ）
2. 対応する `trn_dmm_items` を id IN で取得（title / actress / author / series / maker / genres）

`external_ref` が空の過去投稿は候補に入れない（バックフィルは別タスク）。

### 4.3 スコア（高いほど優先）

同一ブログ＝既に同ジャンル前提。追加の近さ:

| 条件 | 加点 |
|------|------|
| `series` 一致（双方非空） | +100 |
| クレジット（actress / author）の名前集合の積集合あり | +50 |
| `maker` 一致 | +20 |
| `genres` の積集合サイズ × 5（上限 +25） | +0〜25 |
| 新しい `posted_at` | タイブレーク（新しい方を優先） |

v1 は DB 内で完結。埋め込み類似は使わない。

### 4.4 出力

スコア降順 → `posted_at` 降順で上位 `limit` 件。

各要素:

```python
{"title": str, "url": str, "dmm_item_id": str}
```

`title` は投稿時タイトルが status に無いため、`trn_dmm_items.title` を表示用に使う  
（キャッチタイトル整形済みの公開タイトルと多少ずれても v1 は許容。必要なら後で `external_title` 列を検討）。

---

## 5. モジュール構成

```
config/blog_settings.py
  FANZA_HUB / resolve_genre_hub(...)     # または mst 行から組み立て

db/post_repository.py
  mark_post_as_posted(..., external_ref=)
  list_related_blog_posts(account_id, blog_key, exclude_item_id, item_row, limit=3)

db/blog_repository.py
  list_hub_blogs(hub_group) → [{label, public_base_url, floor, blog_id}, ...]
  （livedoor config に public_base_url / genre_label / hub_group を載せる）

livedoor_blog/post.py
  parse_atompub_public_url(response_text) -> str | None
  _related_posts_section_html(related: list[dict]) -> str
  _genre_hub_section_html(hub_links, current_floor|label) -> str
  build_livedoor_blog_html(..., related_posts=, genre_hub=)
  _post_atompub(...) -> str | None   # 公開 URL を返すよう変更

main_livedoor_atompub.py
  投稿前: related / hub を取得して HTML に渡す
  投稿後: mark_post_as_posted(..., external_ref=url)
```

FC2 / Seesaa は今回触らない。`build_livedoor_blog_html` を共有している場合は、引数省略時に⑥⑦が空になるため既存動作を維持。

---

## 6. 設定・フィーチャーフラグ

| 変数 / 設定 | 既定 | 意味 |
|-------------|------|------|
| `LIVEDOOR_RELATED_POSTS` | `1` | `0` で⑥オフ |
| `LIVEDOOR_RELATED_POSTS_LIMIT` | `3` | 最大件数（1〜5 にクランプ） |
| `LIVEDOOR_RELATED_POOL` | `30` | スコア用候補数 |
| `LIVEDOOR_GENRE_HUB` | `1` | `0` で⑦オフ |

マスタに `hub_group` / `public_base_url` が無い環境では⑦は自動で出ない（安全側）。

コード側フォールバック（開発・暫定）として `config/blog_settings.py` に  
`FANZA_GENRE_HUB_BY_ACCOUNT` を置いてもよいが、**本番の正は mst 列**とする。

---

## 7. 処理フロー

```
get_next_livedoor_post
  → build title / body 材料
  → list_related_blog_posts（同 blog_key）
  → list_hub_blogs（hub_group=fanza かつ site=fanza）
  → build_livedoor_blog_html(..., related_posts, genre_hub)
  → post_to_livedoor_blog / _post_atompub
       → 応答から public_url 抽出
  → mark_post_as_posted(item_id, blog_key, external_ref=public_url)
```

**鶏卵**: 初回〜数件は⑥が空。問題ない。URL が貯まるほど⑥が埋まる。

下書き（`LIVEDOOR_ATOMPUB_DRAFT`）のときは:

- `external_ref` を書かない（または書いても関連候補から除外するフラグが必要）
- v1 は **draft 時は external_ref を保存しない**（公開 URL が無い／変わるため）

---

## 8. HTML 仕様（⑥⑦）

スタイルは既存 CTA / プレミアム枠に合わせ、カード過多にしない。リスト＋区切り程度。

```html
<section class="ld-related" style="margin:1.75rem 0;">
  <h2>あわせて読みたい</h2>
  <ul>
    <li><a href="https://.../archives/....html">作品タイトル…</a></li>
  </ul>
</section>

<nav class="ld-genre-hub" style="margin:1.75rem 0;" aria-label="ジャンルから探す">
  <h2>ジャンルから探す</h2>
  <p>
    <a href="https://blog.livedoor.jp/comic-blog/">コミック</a>
    ·
    <a href="https://blog.livedoor.jp/doujin-blog/">同人誌</a>
    ·
    <span>AV</span><!-- 現在地 -->
    ·
    <a href="https://blog.livedoor.jp/amateur-blog/">素人</a>
  </p>
</nav>
```

- タイトルは `html.escape`
- URL は http(s) のみ許可（不正値はスキップ）
- ハブは `public_base_url` をそのまま（末尾スラッシュ正規化は任意）

---

## 9. 実装フェーズ

### Phase 0 — URL 永続化（ブロッカー）

1. `_post_atompub` が公開 URL（なければ None）を返す
2. `post_to_livedoor_blog` が URL を返す
3. `mark_post_as_posted(..., external_ref=)` で保存
4. 単体テスト: Atom XML フィクスチャからの URL 抽出

DDL 変更なし（列既存）。

### Phase 1 — 同ブログ関連記事

1. `list_related_blog_posts`
2. `_related_posts_section_html` + `build_livedoor_blog_html` 接続
3. `main_livedoor_atompub` から呼び出し
4. テスト: スコア順・除外・external_ref 無し・件数0・フラグオフ

### Phase 2 — FANZA ジャンルハブ

1. DDL: `public_base_url` / `genre_label` / `hub_group`
2. `blog_repository` で config に載せる
3. `_genre_hub_section_html` + 接続（site=fanza のみ）
4. テスト: 現在地除外、dmm 非表示、設定不足で非表示

### Phase 3（任意・後回し）

- 過去投稿の `external_ref` バックフィル（AtomPub GET 一覧、または手動 CSV）
- 関連にキャッチタイトル保存
- Seesaa / FC2 横展開
- 近いジャンル同士の「姉妹ブログ TOP」をハブ内で並び最適化（コミック・同人を隣接表示など。リンク先は TOP のまま）

---

## 10. テスト方針

既存ルール（分岐カバレッジ 100%）に合わせる。

| 領域 | 観点 |
|------|------|
| URL 抽出 | alternate あり / xml:base のみ / edit のみ / 不正・空 |
| related 選定 | 0件 / 1件 / 3件超で limit / 自己除外 / ref 無し除外 / series 一致が上位 |
| HTML | セクション有無、escape、フラグオフで空文字 |
| hub | fanza のみ、現在ジャンル非リンク、label 不足行スキップ |

外部 HTTP・Supabase はモック。

---

## 11. 非目標（v1）

- 記事本文での他ジャンル個別記事への相互リンク
- 全投稿の機械的な総当たりリンク
- サイドバー／テンプレート改修（Livedoor テーマ側。アプリは HTML 本文のみ）
- nofollow / sponsored 付与（自ブログ内・ハブ TOP は通常リンク）
- 関連記事の自動更新（過去記事の本文を書き換えてリンク追加）— 新規投稿のみ付与

---

## 12. 運用メモ

1. FANZA のジャンル別ブログ各行に `public_base_url` / `hub_group='fanza'` / 必要なら `genre_label` を入れる
2. Phase 0 デプロイ後、数日分の投稿で `external_ref` が貯まるのを確認
3. Phase 1 で⑥が埋まり始める
4. Phase 2 で⑦を有効化
5. 既存記事への遡及リンクは Phase 3（必要になったら）

---

## 13. 受け入れ条件

- [ ] 新規公開投稿の status に公開 URL が入る（draft 除く）
- [ ] 同ブログに URL 付き投稿が 1 件以上あるとき、新規記事末に最大 3 件の関連が出る
- [ ] 関連は同一 `blog_key` のみ。他ブログ記事 URL は混ざらない
- [ ] FANZA ハブ設定済みブログで、他ジャンル TOP への導線が出る（自ジャンルは非リンクまたは現在地表示）
- [ ] DMM サイトのブログではハブが出ない
- [ ] フラグオフ・データ不足で既存と同等の本文になる（壊れない）
- [ ] 単体テスト追加、`pytest` 分岐カバレッジ要件を維持
