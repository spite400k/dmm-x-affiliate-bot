"""設定の集約エクスポート。

X 用は config.x_settings、ブログ用は config.blog_settings を編集する。
"""

from config.blog_settings import BLOG_ACCOUNT_SETTINGS, LIVEDOOR_BLOG_POST_KEY
from config.x_settings import X_ACCOUNT_SETTINGS

# 後方互換: 旧名は X 用設定を指す
ACCOUNT_SETTINGS = X_ACCOUNT_SETTINGS

__all__ = [
    "ACCOUNT_SETTINGS",
    "BLOG_ACCOUNT_SETTINGS",
    "LIVEDOOR_BLOG_POST_KEY",
    "X_ACCOUNT_SETTINGS",
]
