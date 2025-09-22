import tempfile
from urllib.parse import urlparse
import time
import os
import time
import logging
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------------
# ログ設定
# ---------------------
# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------
# iframe URL から MP4 URL を取得　◎
# ---------------------
def get_mp4_url_from_iframe(iframe_url: str) -> str:

    logger.info(f"iframe URL → {iframe_url}")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")  # ERROR以上のみ表示
    options.add_argument("--disable-logging")  # ログ全体抑制（非公式）

    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(iframe_url)
        time.sleep(5)  # JS のレンダリング待ち
        # iframe に切り替え
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "iframe"))
        )
        driver.switch_to.frame(iframe)

        # video 要素を取得
        video = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )

        mp4_url = video.get_attribute("src")
        print("🎥 video URL:", mp4_url)

        logger.warning(f"⚠️ 抽出した MP4 URL → {mp4_url}")
        return mp4_url
    finally:
        driver.quit()


# ---------------------
# DMM動画ページからMP4取得
# ---------------------
def resolve_mp4_url(page_url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(page_url, headers=headers)
    res.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(res.text, "html.parser")
    source = soup.find("source")
    return source["src"] if source and source.get("src") else None

# ---------------------
# 動画ダウンロード
# ---------------------
def download_video(mp4_url: str, sample_movie_url: str) -> str:

    logger.warning(f"開始")
    # __file__ が存在する場合はそのディレクトリを優先
    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # GitHub Actions 等で __file__ が未定義の場合はこちら
        BASE_DIR = os.getcwd()

    TEMP_DIR = os.path.join(BASE_DIR, "temp")

    logger.warning(f"BASE_DIR {BASE_DIR}")
    logger.warning(f"TEMP_DIR {TEMP_DIR}")

    os.makedirs(TEMP_DIR, exist_ok=True)

    parsed_url = urlparse(mp4_url)
    filename = os.path.basename(parsed_url.path)
    filepath = os.path.join(TEMP_DIR, filename)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Referer": f"{sample_movie_url}"  # ページURLを指定
    }

    res = requests.get(mp4_url, headers=headers, stream=True, timeout=60)

    logger.warning(f"動画取得ステータス → {res.status_code}")

    if res.status_code != 200:
        raise ValueError(f"動画のダウンロードに失敗しました: {mp4_url} (status_code={res.status_code})")
    
    res.raise_for_status()

    logger.warning(f"動画ダウンロード先 → {filepath}")
    total_bytes = 0
    with open(filepath, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total_bytes += len(chunk)

    logger.warning(f"動画サイズ → {total_bytes}")

    if total_bytes == 0:
        raise ValueError(f"ダウンロードしたファイルが空です: {mp4_url}")
    
    logger.info(f"✅ 動画ダウンロード成功: {mp4_url} → {filepath} ({total_bytes} bytes)")
    return filepath


#---------------------
# サンプル動画取得＆アップロード
#---------------------
def get_sample_movie(url: str) -> str:
    """サンプル動画をダウンロードして一時ファイルのパスを返す"""
    # 共通の一時ディレクトリを利用（自動的にOS依存のパスになる）
    temp_dir = tempfile.gettempdir()
    
    # URLからファイル名を決定（最後の部分が空ならデフォルト名）
    filename = os.path.basename(url.split("?")[0]) or "sample.mp4"
    abs_path = os.path.join(temp_dir, filename)

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(abs_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return abs_path
    except Exception as e:
        raise Exception(f"動画ダウンロード失敗: {url} → {e}")