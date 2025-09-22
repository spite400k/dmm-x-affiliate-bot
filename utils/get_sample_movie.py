from urllib.parse import urlparse
import time
import os
import time
import logging
from httpcore import TimeoutException
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

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
# iframe URL から MP4 URL を取得 ◎
# ---------------------
def get_mp4_url_from_iframe(iframe_url: str) -> str:
    logger.info(f"🌐 iframe URL 開始 → {iframe_url}")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logger.debug("🚀 ページ読み込み開始")
        driver.get(iframe_url)
        time.sleep(3)  # JSレンダリング待ち

        # 年齢認証
        try:
            button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//a[text()='はい'] | //a[text()='I Agree']"
                ))
            )
            driver.execute_script("arguments[0].click();", button)
            logging.info("年齢認証成功")
            time.sleep(2)
        except (TimeoutException, StaleElementReferenceException):
            logging.info("年齢認証不要 or 既認証済み")

        logger.debug("🔎 iframe 探索中...")
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "iframe"))
        )
        logger.info(f"✅ iframe 発見: {iframe.get_attribute('src')}")

        driver.switch_to.frame(iframe)
        logger.debug("🔄 iframe に切り替え完了")

        logger.debug("🎥 video 要素探索中...")
        video = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )
        logger.info("✅ video タグ発見")

        mp4_url = video.get_attribute("src")
        if mp4_url:
            logger.warning(f"⚠️ 抽出した MP4 URL → {mp4_url}")
        else:
            logger.error("❌ video タグはあるが src が空")

        return mp4_url

    except Exception as e:
        logger.exception(f"🔥 例外発生: {type(e).__name__} → {e}")
        return None

    finally:
        logger.debug("🛑 WebDriver 終了")
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

    logger.warning(f"⚠️ 動画取得ステータス → {res.status_code}")

    if res.status_code != 200:
        raise ValueError(f"動画のダウンロードに失敗しました: {mp4_url} (status_code={res.status_code})")
    
    res.raise_for_status()

    logger.warning(f"⚠️ 動画ダウンロード先 → {filepath}")
    total_bytes = 0
    with open(filepath, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total_bytes += len(chunk)

    logger.warning(f"⚠️ 動画サイズ → {total_bytes}")

    if total_bytes == 0:
        raise ValueError(f"ダウンロードしたファイルが空です: {mp4_url}")
    
    logger.info(f"✅ 動画ダウンロード成功: {mp4_url} → {filepath} ({total_bytes} bytes)")
    return filepath


#---------------------
# サンプル動画取得＆アップロード
#---------------------
def get_sample_movie(sample_movie_url):
    logger.info(f"動画URLあり → {sample_movie_url}")
    video_path = ""
    try:
            # HTMLページURLならMP4を抽出
        if sample_movie_url.endswith(".html") or "litevideo" in sample_movie_url:
            logger.info(f"HTMLページURLと判断 → MP4抽出へ")
            mp4_url = get_mp4_url_from_iframe(sample_movie_url)

        logger.info(f"抽出したMP4 URL → {mp4_url}")
            # 動画をダウンロードしてアップロード
        video_path = download_video(mp4_url, sample_movie_url)
        logger.info(f"✅ 動画処理成功 → {video_path}")

    except Exception as e:
        logger.warning(f"⚠️ 動画処理失敗 → {e}")

    return video_path
