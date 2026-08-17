"""Livedoor キャッチタイトル（スマホ新着向け）の単体テスト。"""

from __future__ import annotations

import pytest

from livedoor_blog.post import (
    _ATOMPUB_TITLE_MAX_CHARS,
    _CATCHY_MOBILE_VISIBLE,
    _build_amateur_av_catchy_title,
    _build_comic_mobile_catchy_title,
    _build_mobile_catchy_title,
    _build_photo_mobile_catchy_title,
    _comic_work_title,
    _extract_quoted_work_title,
    _fit_photo_name_work_lead,
    _fit_pipe_lead,
    _photobook_work_title,
    _strip_edition_noise,
    _strip_trailing_credit,
    _title_hook_front,
    blog_post_title_for_item,
)


@pytest.fixture(autouse=True)
def _catchy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEDOOR_CATCHY_TITLE", "1")


def test_hook_front_keeps_first_sentence() -> None:
    raw = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    assert _title_hook_front(raw) == "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。"


def test_strip_trailing_credit() -> None:
    core = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    assert _strip_trailing_credit(core, ["明日葉みつは"]) == (
        "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る"
    )


def test_mobile_catchy_leads_with_actress() -> None:
    core = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    got = _build_mobile_catchy_title(core, ["明日葉みつは"])
    assert got.startswith("明日葉みつは｜")
    assert "高身長の貧困女学生" in got
    assert got.endswith("｜レビュー")
    assert len(got) <= _ATOMPUB_TITLE_MAX_CHARS


def test_blog_post_title_for_item_with_actress() -> None:
    title = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    item = {"actress": [{"name": "明日葉みつは"}], "service": "digital"}
    got = blog_post_title_for_item(title, item)
    assert got.startswith("明日葉みつは｜高身長")
    assert "｜レビュー" in got


def test_blog_post_title_off_returns_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEDOOR_CATCHY_TITLE", "0")
    title = "長い商品名そのままです。"
    assert blog_post_title_for_item(title, {"actress": "誰か"}) == title


def test_blog_post_title_without_credit_still_shortens() -> None:
    title = (
        "ガテン女上司と突然の豪雨で現場から帰れなくなり…"
        "カラダを温めあううち色っぽい濡れ髪濡れ肌に理性爆発ワゴン車内"
    )
    got = blog_post_title_for_item(title, {"service": "digital"})
    assert got.endswith("｜レビュー")
    assert len(got) < len(title) + 10
    # 先頭フックが残っている
    assert got.startswith("ガテン女上司")


def test_extract_quoted_work_title() -> None:
    assert _extract_quoted_work_title("菊地ひな『グラビアバイブル』レビュー") == (
        "グラビアバイブル"
    )
    assert _extract_quoted_work_title("市川愛美 「純愛」 写真集") == "純愛"
    assert _extract_quoted_work_title("括弧なしタイトル") == ""


def test_photobook_work_title_prefers_quotes() -> None:
    core = "いじらしさと大人っぽさがまぶしい…『初写真集』 白石真菜"
    assert _photobook_work_title(core, ["白石真菜"]) == "初写真集"


def test_photobook_work_title_falls_back_to_core() -> None:
    core = "ひなぼーる ぷっくりおしりとみずみずしい肌 菊地ひな"
    assert _photobook_work_title(core, ["菊地ひな"]) == (
        "ひなぼーる ぷっくりおしりとみずみずしい肌"
    )


def test_fit_photo_name_work_lead_fits_mobile_visible() -> None:
    lead = _fit_photo_name_work_lead("菊地ひな", "グラビアバイブル")
    assert lead == "菊地ひな｜『グラビアバイブル』"
    assert len(lead) <= _CATCHY_MOBILE_VISIBLE


def test_fit_photo_name_work_lead_truncates_long_work() -> None:
    long_work = "とても長い写真集のタイトルで可視枠を超えそうな名前です"
    lead = _fit_photo_name_work_lead("篠崎愛", long_work)
    assert lead.startswith("篠崎愛｜『")
    assert lead.endswith("』")
    assert len(lead) <= _CATCHY_MOBILE_VISIBLE


def test_build_photo_mobile_catchy_title() -> None:
    got = _build_photo_mobile_catchy_title(
        "菊地ひな『グラビアバイブル』公式ガイド",
        ["菊地ひな"],
    )
    assert got.startswith("菊地ひな｜『グラビアバイブル』")
    assert got.endswith("｜レビュー")
    assert len(got[:_CATCHY_MOBILE_VISIBLE]) <= _CATCHY_MOBILE_VISIBLE
    # 可視枠内に人名と作品名が含まれる
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "菊地ひな" in visible
    assert "グラビアバイブル" in visible


def test_blog_post_title_photo_uses_name_and_work() -> None:
    title = "いじらしさと大人っぽさがまぶしい…白石真菜『初写真集』"
    item = {
        "service": "ebook",
        "floor": "photo",
        "author": [{"name": "白石真菜"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("白石真菜｜『初写真集』")
    assert got.endswith("｜レビュー")
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "白石真菜" in visible
    assert "初写真集" in visible


def test_ebook_photo_bonus_keeps_name_work_in_front() -> None:
    """電子特典でも【電子版…】を先頭に付けず、人名｜作品名を可視枠に残す。"""
    title = "【電子版限定特典付き】なにかの写真集タイトルがとても長い場合の例です 誰か"
    item = {
        "service": "ebook",
        "floor": "photo",
        "author": [{"name": "誰か"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("誰か｜『")
    assert "電子特典レビュー" in got
    assert not got.startswith("【電子版")
    assert len(got) <= _ATOMPUB_TITLE_MAX_CHARS
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "誰か" in visible


def test_ebook_comic_bonus_keeps_author_work_in_front() -> None:
    """漫画の電子特典でも【電子版…】を先頭に付けず、作者｜作品名を可視枠に残す。"""
    title = "【電子版限定特典付き】なにかのコミックタイトルがとても長い場合の例です 誰か"
    item = {
        "service": "ebook",
        "floor": "comic",
        "author": [{"name": "誰か"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("誰か｜『")
    assert "電子特典レビュー" in got
    assert "【電子版描き下ろし】" not in got
    assert len(got) <= _ATOMPUB_TITLE_MAX_CHARS
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "誰か" in visible


def test_strip_edition_noise_drops_fanza_and_tankawa() -> None:
    raw = "秘め妻【デジタル特装版】【FANZA限定版】"
    assert _strip_edition_noise(raw) == "秘め妻"
    assert _strip_edition_noise("メイド教育。ー没落貴族 瑠璃川椿ー(単話)") == (
        "メイド教育。ー没落貴族 瑠璃川椿ー"
    )
    assert _strip_edition_noise("VIP限定 SEXバーへようこそ モザイク版") == (
        "VIP限定 SEXバーへようこそ"
    )


def test_comic_work_title_uses_first_clause() -> None:
    core = "メイド教育。ー没落貴族 瑠璃川椿ー(単話)"
    assert _comic_work_title(core, []) == "メイド教育"


def test_build_comic_mobile_catchy_title() -> None:
    got = _build_comic_mobile_catchy_title(
        "秘め妻【デジタル特装版】【FANZA限定版】",
        ["某作者"],
    )
    assert got.startswith("某作者｜『秘め妻』")
    assert got.endswith("｜レビュー")
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "某作者" in visible
    assert "秘め妻" in visible
    assert "FANZA" not in visible
    assert "デジタル特装" not in visible


def test_blog_post_title_comic_uses_author_and_work() -> None:
    title = "残クレアルフォード元ヤン人妻（32歳３人子持ちママ）を家に連れ込んだら"
    item = {
        "service": "ebook",
        "floor": "comic",
        "author": [{"name": "山田太郎"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("山田太郎｜『")
    assert got.endswith("｜レビュー")
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "山田太郎" in visible
    assert "FANZA" not in got
    assert "【デジタル" not in got


def test_blog_post_title_doujin_uses_circle_maker() -> None:
    title = "VIP限定 SEXバーへようこそ モザイク版"
    item = {
        "service": "doujin",
        "floor": "digital_doujin",
        "maker": "某サークル",
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("某サークル｜『VIP限定 SEXバーへようこそ』")
    assert got.endswith("｜レビュー")
    assert "モザイク版" not in got
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "某サークル" in visible


def test_blog_post_title_doujin_prefers_author_over_maker() -> None:
    title = "生殖のため生まれた猿ども (単話)"
    item = {
        "service": "doujin",
        "floor": "digital_doujin",
        "author": [{"name": "著者A"}],
        "maker": "サークルB",
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("著者A｜『生殖のため生まれた猿ども』")
    assert "サークルB" not in got
    assert "単話" not in got


def test_fit_pipe_lead_keeps_series_attr_name() -> None:
    got = _fit_pipe_lead(["シロウトTV", "人妻", "みなみ"])
    assert got == "シロウトTV｜人妻｜みなみ"
    assert len(got) <= _CATCHY_MOBILE_VISIBLE


def test_fit_pipe_lead_truncates_long_series() -> None:
    long_series = "とても長いシリーズ名で可視枠を超えそうなレーベルです"
    got = _fit_pipe_lead([long_series, "みなみ"])
    assert "みなみ" in got
    assert len(got) <= _CATCHY_MOBILE_VISIBLE


def test_build_amateur_av_catchy_uses_series_and_attr() -> None:
    item = {
        "service": "digital",
        "floor": "videoc",
        "series": "シロウトTV",
        "genres": ["人妻", "素人"],
        "actress": [{"name": "みなみ"}],
    }
    got = _build_amateur_av_catchy_title("みなみ", item, ["みなみ"])
    assert got.startswith("シロウトTV｜人妻｜みなみ")
    assert got.endswith("｜レビュー")
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "シロウトTV" in visible
    assert "みなみ" in visible
    assert got != "みなみ｜レビュー"


def test_blog_post_title_videoc_avoids_name_only() -> None:
    title = "みな"
    item = {
        "service": "digital",
        "floor": "videoc",
        "actress": [{"name": "みな"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.endswith("｜レビュー")
    assert got != "みな｜レビュー"
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "素人" in visible
    assert "みな" in visible


def test_blog_post_title_videoc_mirei_with_hatsudori() -> None:
    title = "MIREI"
    item = {
        "service": "digital",
        "floor": "videoc",
        "actress": [{"name": "MIREI"}],
        "genres": ["初撮り", "素人"],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("初撮り｜MIREI")
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "初撮り" in visible
    assert "MIREI" in visible


def test_blog_post_title_videoc_two_names() -> None:
    title = "ゆみ＆ひなこ"
    item = {
        "service": "digital",
        "floor": "videoc",
        "series": "ラグジュTV",
        "actress": [{"name": "ゆみ"}, {"name": "ひなこ"}],
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("ラグジュTV｜")
    assert "ゆみ＆ひなこ" in got
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "ラグジュTV" in visible


def test_blog_post_title_videoa_amateur_signal() -> None:
    title = "素人ナンパ 虹野"
    item = {
        "service": "digital",
        "floor": "videoa",
        "actress": [{"name": "虹野"}],
        "genres": ["素人", "ナンパ"],
    }
    got = blog_post_title_for_item(title, item)
    assert got != "虹野｜レビュー"
    visible = got[:_CATCHY_MOBILE_VISIBLE]
    assert "ナンパ" in visible or "素人" in visible


def test_blog_post_title_videoa_pro_keeps_actress_hook() -> None:
    title = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    item = {
        "actress": [{"name": "明日葉みつは"}],
        "service": "digital",
        "floor": "videoa",
    }
    got = blog_post_title_for_item(title, item)
    assert got.startswith("明日葉みつは｜高身長")
    assert "｜レビュー" in got
