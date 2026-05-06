"""
ライブドアブログへ AtomPub API だけで1件投稿するスタンドアロンスクリプト。

main.py と同じ livedoor_blog.post を使います。.env に次を設定してください。
  LIVEDOOR_ID
  LIVEDOOR_ATOMPUB_PASSWORD  （ブログ設定 > その他 > API Key の AtomPub用）
  LIVEDOOR_BLOG_NAME           （例: yorunoosusume.doorblog.jp なら yorunoosusume）

使用例:
  python post_livedoor_atompub.py "記事タイトル" --body "<p>本文HTML</p>"
  python post_livedoor_atompub.py "タイトル" --body-file article.html
  python post_livedoor_atompub.py "下書き" --body "<p>...</p>" --draft
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from livedoor_blog.post import post_to_livedoor_blog

logger = logging.getLogger(__name__)


def _require_env(names: tuple[str, ...]) -> None:
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        print(
            "次の環境変数（または .env）が必要です: " + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="ライブドアブログ AtomPub で記事を1件投稿します。",
    )
    parser.add_argument("title", help="記事タイトル（プレーンテキスト）")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--body",
        dest="body",
        help="記事本文（HTML。CDATA 内に入るため ]]></ 系に注意）",
    )
    g.add_argument(
        "--body-file",
        dest="body_file",
        metavar="PATH",
        help="本文HTMLを読み込むファイル（UTF-8）",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="下書きとして投稿（LIVEDOOR_ATOMPUB_DRAFT を一時的に有効化）",
    )
    args = parser.parse_args()

    if args.body_file:
        path = os.path.abspath(args.body_file)
        with open(path, encoding="utf-8") as f:
            body_html = f.read()
    else:
        body_html = args.body or ""

    # このスクリプトでは AtomPub のみ（main の LIVEDOOR_BLOG_ENABLED に依存しない）
    os.environ["LIVEDOOR_BLOG_ENABLED"] = "1"
    os.environ["LIVEDOOR_POST_METHOD"] = "atompub"
    if args.draft:
        os.environ["LIVEDOOR_ATOMPUB_DRAFT"] = "1"

    _require_env(
        ("LIVEDOOR_ID", "LIVEDOOR_ATOMPUB_PASSWORD", "LIVEDOOR_BLOG_NAME"),
    )

    try:
        post_to_livedoor_blog(args.title, body_html)
    except Exception as e:
        logger.exception("投稿に失敗しました: %s", e)
        sys.exit(1)

    logger.info("投稿が完了しました: %s", args.title)


if __name__ == "__main__":
    main()
