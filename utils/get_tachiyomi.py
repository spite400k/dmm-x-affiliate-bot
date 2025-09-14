import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from PIL import Image

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d | %(message)s"
)

def save_page_source(driver, idx, log_dir="logs"):
    # ログディレクトリがなければ作成
    os.makedirs(log_dir, exist_ok=True)

    # ファイル名に idx をつける
    log_file = os.path.join(log_dir, f"page_source_{idx}.html")

    # ページソースを保存
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    print(f"✅ ページソースを保存しました: {log_file}")

# ---------------------
# 表示中のcanvas取得関数
# ---------------------
def get_visible_canvas(driver):
    logging.debug("canvas探索開始")
    candidates = driver.find_elements(By.CSS_SELECTOR, "canvas")
    logging.debug(f"候補canvas数: {len(candidates)}")

    for i, c in enumerate(candidates):
        try:
            visible = c.is_displayed()
            logging.debug(f"canvas[{i}] visible={visible}, size={c.size}, location={c.location}")
            if visible:
                return c
        except Exception as e:
            logging.warning(f"canvas[{i}] 可視チェック失敗: {e}")
    raise Exception("表示中のcanvasが見つかりません")

# ---------------------
# ページカウンタ取得関数
# ---------------------
def get_page_counter(driver, timeout=30):
    """pageSliderCounter から現在/総ページ数を取得する（非表示でもOK）"""
    try:
        counter_elem = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, "pageSliderCounter"))
        )
        logging.info(f"取得した counter_elem: '{counter_elem.get_attribute('outerHTML')}'")

        counter_text = counter_elem.text.strip()  # e.g., "1/27"
        logging.info(f"取得した pageSliderCounter: '{counter_text}'")

        if "/" in counter_text:
            current_page, total_page = map(int, counter_text.split("/"))
            return current_page, total_page
        else:
            logging.warning(f"ページカウンタの形式が不正: '{counter_text}'")
            with open("debug_get_page_counter1.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.save_screenshot("debug_get_page_counter1.png")
            return 1, 50  # 仮値
    except Exception as e:
        logging.error(f"ページカウンタ取得失敗: {e}")
        with open("debug_get_page_counter.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.save_screenshot("debug_get_page_counter.png")
        return 1, 50


# ---------------------
# Tachiyomiページキャプチャ関数
# ---------------------
def capture_all_tachiyomi_pages(tachiyomi_url: str):
    logging.info(f"立ち読み対象URL: {tachiyomi_url}")

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)

    output_pdf_path = os.path.join(BASE_DIR, "tachiyomi_pages.pdf")

    options = Options()
    options.add_argument("--headless=new")  # 新しいヘッドレスモード
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=440,932")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) \
                            AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info("DMMトップページを開く")
        driver.get("https://www.dmm.co.jp/top/")

        # with open("debug1.html", "w", encoding="utf-8") as f:
        #     f.write(driver.page_source)
        # driver.save_screenshot("debug1.png")   
        # logging.info("debug1.html 保存完了")

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
            # with open("debug2.html", "w", encoding="utf-8") as f:
            #     f.write(driver.page_source)
            # driver.save_screenshot("debug2.png")
            time.sleep(2)
        except (TimeoutException, StaleElementReferenceException):
            logging.info("年齢認証不要 or 既認証済み")
            # with open("debug1_e.html", "w", encoding="utf-8") as f:
            #     f.write(driver.page_source)
            # driver.save_screenshot("debug1_e.png")

        try:
            # logging.info("試し読みページを開く")
            driver.get(tachiyomi_url)
            # logging.info("試し読みページを開く完了")
        except Exception as e:
            logging.error(f"driver.get 失敗: {e}")
            raise

        time.sleep(5)

        images = []
        page_idx = 1
        current_page = 0

        # logging.info("viewer要素を待機")
        # viewer要素にフォーカス
        viewer = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "viewer"))
        )
        # driver.save_screenshot("debug3.png")  

        WebDriverWait(driver, 30).until_not(
            EC.visibility_of_any_elements_located((By.CSS_SELECTOR, ".loadingImage"))
        )
        # driver.save_screenshot("debug4.png")  

        _, total_page = get_page_counter(driver)
        logging.info(f"総ページ数: {total_page}")

        actions = ActionChains(driver)
        # logging.info("viewer要素をクリックしてフォーカス")

        # viewer.click()
        # driver.save_screenshot("debug7.png")  
        time.sleep(5)  # ページ描画待ち
        # logging.info("初期ページ描画待ち完了")


        while True:
            try:
                logging.info(f"=== ページ処理開始 idx={page_idx}, 現在={current_page}, 総数={total_page} ===")
                # ページ処理の最後にチェックを追加
                try:
                    purchase_button = WebDriverWait(driver, 30).until(
                        # EC.presence_of_element_located(By.XPATH, "//span[text()='購入する']")
                        EC.presence_of_element_located((By.ID, "endOfBook"))
                    )

                    if purchase_button.is_displayed():
                        logging.info("最終ページを検出 → スクリーンショット終了")
                        break
                except:
                    # 要素がない場合はエラーになるので無視して続行
                    # logging.info("最終ページではないようです → 続行")
                    pass

                canvas = WebDriverWait(driver, 5).until(lambda d: get_visible_canvas(d))
                screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx:03}.png")
                canvas.screenshot(screenshot_path)
                images.append(screenshot_path)
                logging.info(f"保存成功: {screenshot_path}")

                # ページ番号更新
                if current_page == 0:
                    current_page, _ = get_page_counter(driver)

                if current_page >= total_page:
                    logging.info("最後のページに到達 → 終了")
                    break

                logging.debug("次ページへ移動 (ARROW_LEFT)")
                actions.send_keys(Keys.ARROW_LEFT).perform()
                page_idx += 1
                current_page += 1
                time.sleep(1)

            except (TimeoutException, NoSuchElementException) as e:
                logging.error(f"canvas取得失敗 idx={page_idx}: {e}")
                save_page_source(driver, idx=page_idx)  # ページソース保存
                break
            except Exception as e:
                logging.exception(f"予期せぬエラー idx={page_idx}: {e}")
                save_page_source(driver, idx=page_idx)
                break

        # 画像をPDF化
        if images:
            try:
                pil_images = [Image.open(p).convert("RGB") for p in images]
                pil_images[0].save(output_pdf_path, save_all=True, append_images=pil_images[1:])
                images.append(output_pdf_path)
                logging.info(f"PDF保存完了: {output_pdf_path}")
            except Exception as e:
                logging.exception(f"PDF保存失敗: {e}")
        else:
            logging.warning("画像が1枚も取得できなかったためPDF作成はスキップ")

    finally:
        driver.quit()

    return images


if __name__ == "__main__":
    test_url = "https://book.dmm.co.jp/tachiyomi/?cid=FRNfXRNVFW1RAQxaBwFUVgMLU1gAClAPVU5EDl0VClQMBllNB1o*UFcKWhRHVwVfCBxZW1kEVQ__&lin=1&sd=0"
    capture_all_tachiyomi_pages(test_url)
