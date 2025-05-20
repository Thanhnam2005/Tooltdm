import time
import re
import os
import random
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import tempfile
from urllib.parse import quote_plus

# --- Cấu hình Chung ---
URL_FACEBOOK_LOGIN = "https://www.facebook.com"
URL_2FA_LIVE = "https://2fa.live"
URL_FACEBOOK_TRADEMARK_FORM = "https://en-gb.facebook.com/help/contact/trademarkform?locale2=en_gb"
URL_USPTO_SEARCH = "https://tmsearch.uspto.gov/search/search-results"
URL_WEBMAIL = "https://webmail.la-girl.com" # Thay thế bằng URL webmail thực của bạn

EMAIL_DATA_FILE = "email.txt"
LIST_FILE_INPUT = "list.txt"
REUP_ACCOUNT_FILE = "reup.txt"
ADDITIONAL_INFO_FILE = "form.txt"
PHOTOS_DOWNLOAD_FOLDER = r"F:\TOOL\autobq\photos" # Đảm bảo đường dẫn này tồn tại và có quyền ghi

FB_FORM_POSTAL_ADDRESS = "United States"
FB_FORM_TRADEMARK_REG_COUNTRY = "United States"

reup_fb_tab_handle = None
is_reup_fb_logged_in = False

def configure_main_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    # User agent nên được cập nhật định kỳ để giống trình duyệt mới
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-notifications")
    options.add_argument('--lang=en-US') # Giữ ngôn ngữ trình duyệt là tiếng Anh
    options.add_experimental_option('prefs', {
        'intl.accept_languages': 'en-US,en', # Ngôn ngữ ưu tiên của trang web
        "profile.default_content_setting_values.media_stream_mic": 2,
        "profile.default_content_setting_values.media_stream_camera": 2,
        "profile.default_content_setting_values.geolocation": 2,
        "profile.default_content_setting_values.notifications": 2
    })
    try:
        print("Đang khởi tạo WebDriver...");
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("WebDriver đã khởi tạo.")
        if not os.path.exists(PHOTOS_DOWNLOAD_FOLDER):
            try:
                os.makedirs(PHOTOS_DOWNLOAD_FOLDER)
                print(f"Đã tạo thư mục: {PHOTOS_DOWNLOAD_FOLDER}")
            except Exception as e_mkdir:
                print(f"LỖI khi tạo thư mục {PHOTOS_DOWNLOAD_FOLDER}: {e_mkdir}. Vui lòng tạo thủ công.")
        return driver
    except Exception as e:
        print(f"Lỗi WebDriver: {e}");
        return None

def remove_duplicates_in_wordmark(wordmark_text):
    words = wordmark_text.split(); seen_upper = set(); unique_words_original_case = []
    for word in words:
        if not word: continue
        if word.upper() not in seen_upper:
            seen_upper.add(word.upper())
            unique_words_original_case.append(word)
    return ' '.join(unique_words_original_case)

def robust_click(driver, wait, by_type, locator_value, description, timeout=15):
    element = None; final_wait = WebDriverWait(driver, timeout)
    try:
        element = final_wait.until(EC.element_to_be_clickable((by_type, locator_value)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element); time.sleep(0.3)
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        if element:
            try: element.click(); return True
            except Exception as e2:
                if timeout > 3 : print(f"   RobustClick: Lỗi click tự nhiên '{description}': {type(e2).__name__}")
        elif timeout > 3 : print(f"   RobustClick: Hoàn toàn thất bại '{description}' (target: {locator_value})")
        return False

def check_and_close_cover_photo_error(driver, stage_name=""):
    """Kiểm tra và cố gắng đóng pop-up lỗi 'cover photo too small'."""
    try:
        cover_photo_error_dialog_xpath = "//div[@role='dialog'][.//div[contains(text(),'Please choose a different cover photo') or contains(text(),'This cover photo is too small')]]"
        error_dialog_wait = WebDriverWait(driver, 3)
        
        # Sửa: Không cần gán lại error_dialog_elements nếu WebDriverWait thành công
        error_dialog_wait.until(
            EC.presence_of_all_elements_located((By.XPATH, cover_photo_error_dialog_xpath))
        )
        # Nếu không có TimeoutException, nghĩa là dialog đã được tìm thấy
        print(f"ReupPost: CẢNH BÁO ({stage_name}) - Phát hiện pop-up 'cover photo too small'. Đang cố gắng đóng...")
        try: driver.save_screenshot(f"cover_photo_error_detected_{stage_name}_{time.strftime('%Y%m%d%H%M%S')}.png")
        except: pass

        close_x_button_xpath = f"{cover_photo_error_dialog_xpath}//div[@aria-label='Close'][@role='button']"
        close_text_button_xpath = f"{cover_photo_error_dialog_xpath}//div[@role='button'][normalize-space()='Close' or .//div[normalize-space()='Close'] or .//span[normalize-space()='Close']]"
        closed_popup = False

        if robust_click(driver, WebDriverWait(driver, 2), By.XPATH, close_x_button_xpath, f"Nút X đóng pop-up ({stage_name})", timeout=2):
            closed_popup = True
        elif robust_click(driver, WebDriverWait(driver, 2), By.XPATH, close_text_button_xpath, f"Nút 'Close' text đóng pop-up ({stage_name})", timeout=2):
            closed_popup = True
        
        if closed_popup:
            print(f"ReupPost: Đã đóng pop-up 'cover photo too small' ({stage_name}) bằng click.")
            time.sleep(1.5)
            return True 
        else:
            print(f"ReupPost: KHÔNG đóng được pop-up 'cover photo too small' ({stage_name}) bằng click. Thử ESCAPE.")
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                print(f"ReupPost: Đã thử nhấn ESCAPE để đóng pop-up ({stage_name}).")
                time.sleep(1.5)
                if not driver.find_elements(By.XPATH, cover_photo_error_dialog_xpath): # Kiểm tra lại
                    print(f"ReupPost: ESCAPE có vẻ đã đóng được pop-up ({stage_name}).")
                else:
                    print(f"ReupPost: ESCAPE không đóng được pop-up ({stage_name}).")
                return True # Vẫn trả về True vì đã phát hiện và cố gắng xử lý
            except Exception as e_esc:
                print(f"ReupPost: Lỗi khi thử nhấn ESCAPE ({stage_name}): {e_esc}")
                return True # Vẫn trả về True vì đã phát hiện và cố gắng xử lý
    except TimeoutException:
        return False
    except Exception as e_popup_check:
        print(f"ReupPost: Lỗi khi kiểm tra pop-up 'cover photo too small' ({stage_name}): {type(e_popup_check).__name__} - {e_popup_check}")
        return False

# ... (Nội dung các hàm get_2fa_code_from_2falive, execute_facebook_reup_login_once được giữ nguyên) ...
def get_2fa_code_from_2falive(driver, wait_medium, current_fb_tab_handle, two_fa_secret_key):
    print("   Reup 2FA: Mở tab 2fa.live...")
    original_tabs_before_2falive = set(driver.window_handles)
    driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
    live_2fa_tab = next((h for h in driver.window_handles if h not in original_tabs_before_2falive), None)
    if not live_2fa_tab: print("   Reup 2FA: LỖI - Không mở được tab 2fa.live."); return None
    driver.switch_to.window(live_2fa_tab); driver.get(URL_2FA_LIVE)
    code_6_digits = None
    try:
        wait_medium.until(EC.visibility_of_element_located((By.ID, "listToken"))).send_keys(two_fa_secret_key)
        if not robust_click(driver, wait_medium, By.ID, "submit", "Nút Submit trên 2fa.live"): raise Exception("Không click được submit trên 2fa.live")
        code_text = WebDriverWait(driver, 10).until(
            lambda d: d.find_element(By.ID, "output").get_attribute("value") if '|' in d.find_element(By.ID, "output").get_attribute("value") else None,
            "Output 2fa.live không chứa '|' sau 10s"
        )
        if code_text:
            parts = code_text.strip().splitlines()[-1].split('|')
            if len(parts) == 2:
                extracted_code = parts[1].strip()[-6:]
                if extracted_code.isdigit() and len(extracted_code) == 6:
                    code_6_digits = extracted_code; print(f"   Reup 2FA: Lấy được mã: {code_6_digits}")
            if not code_6_digits: print(f"   Reup 2FA: Không trích xuất mã từ output: '{code_text}'")
        else: print(f"   Reup 2FA: Không lấy được giá trị từ output hoặc không có dấu '|'.")
    except Exception as e: print(f"   Reup 2FA: Lỗi khi thao tác trên 2fa.live: {e}")
    finally:
        if driver.current_window_handle == live_2fa_tab and live_2fa_tab in driver.window_handles : driver.close()
        if current_fb_tab_handle in driver.window_handles: driver.switch_to.window(current_fb_tab_handle)
        elif driver.window_handles: driver.switch_to.window(driver.window_handles[0])
    return code_6_digits

def execute_facebook_reup_login_once(driver, wait_medium, wait_long, username, password, two_fa_secret, profile_slug_for_redirect):
    global reup_fb_tab_handle, is_reup_fb_logged_in
    if is_reup_fb_logged_in:
        if reup_fb_tab_handle and reup_fb_tab_handle in driver.window_handles:
            driver.switch_to.window(reup_fb_tab_handle)
            target_profile_url = f"https://www.facebook.com/{profile_slug_for_redirect}"
            if profile_slug_for_redirect.lower() not in driver.current_url.lower():
                print(f"Reup: Đã đăng nhập, điều hướng lại đến {target_profile_url}")
                driver.get(target_profile_url); time.sleep(2)
            return True
        else: is_reup_fb_logged_in = False; print("Reup: Tab Reup FB đã bị đóng, cần đăng nhập lại.")

    print("\nReup: Bắt đầu đăng nhập Facebook (một lần)...")
    original_tabs_before_reup_tab = set(driver.window_handles)
    caller_tab_handle = driver.current_window_handle
    driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
    newly_opened_reup_tabs = [h for h in driver.window_handles if h not in original_tabs_before_reup_tab]
    if not newly_opened_reup_tabs:
        print("   Reup: LỖI - Không thể mở tab mới cho Reup.");
        if caller_tab_handle in driver.window_handles: driver.switch_to.window(caller_tab_handle)
        return False
    reup_fb_tab_handle = newly_opened_reup_tabs[0]
    driver.switch_to.window(reup_fb_tab_handle)
    driver.get(URL_FACEBOOK_LOGIN); print(f"Reup: Đã mở URL FB Login: {URL_FACEBOOK_LOGIN}")
    try:
        wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='email']"))).send_keys(username)
        wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='pass']"))).send_keys(password)
        if not robust_click(driver, wait_medium, By.XPATH, "//button[@name='login']", "Nút Đăng nhập Facebook"): raise Exception("Không click được nút Đăng nhập")
        print("Reup: Đã nhấn Đăng nhập. Chờ xử lý 2FA (10 giây)..."); time.sleep(10)
        two_fa_flow_completed_successfully = False
        try:
            direct_code_input_xpaths = ["//input[@id='approvals_code']", "//input[@type='text'][@name='approvals_code']", "//input[@type='text'][normalize-space(@aria-label)='Login code' or normalize-space(@aria-label)='Security code' or normalize-space(@aria-label)='Mã đăng nhập']"]
            direct_code_input_field = next((WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.XPATH, xpath))) for xpath in direct_code_input_xpaths if driver.find_elements(By.XPATH, xpath)), None)
            if direct_code_input_field:
                print(f"Reup: Tìm thấy ô nhập mã 2FA trực tiếp.")
                code_6_digits = get_2fa_code_from_2falive(driver, wait_medium, driver.current_window_handle, two_fa_secret)
                if not code_6_digits: print("Reup: LỖI - Không lấy được mã 2FA (cho ô trực tiếp)."); return False
                direct_code_input_field.send_keys(code_6_digits); print(f"Reup: Đã điền mã 2FA trực tiếp: {code_6_digits}"); time.sleep(0.5)
                continue_after_code_xpath = "//div[@role='button' or @role='none'][contains(@class,'xti2d7y')][descendant::span[normalize-space()='Continue']]"
                continue_after_code_fallback_xpath = "(//div[@role='button'][descendant::span[normalize-space()='Continue']])[last()]"
                if robust_click(driver, wait_medium, By.XPATH, continue_after_code_xpath, "Nút 'Continue' (xti2d7y) sau mã 2FA", timeout=15): print("Reup: Đã nhấn Continue (xti2d7y) sau mã 2FA (direct)."); time.sleep(3)
                elif robust_click(driver, wait_medium, By.XPATH, continue_after_code_fallback_xpath, "Nút 'Continue' sau mã 2FA (fallback)", timeout=15): print("Reup: Đã nhấn Continue (fallback) sau mã 2FA (direct)."); time.sleep(3)
                else: print("Reup: Không click được Continue sau mã 2FA trực tiếp.")
                two_fa_flow_completed_successfully = True
        except Exception as e_direct_2fa: print(f"Reup: Không tìm thấy/xử lý ô nhập mã 2FA trực tiếp, hoặc lỗi: {type(e_direct_2fa).__name__}")

        if not two_fa_flow_completed_successfully:
            try:
                try_another_way_xpath = "//div[@role='button' and (descendant::span[contains(normalize-space(),'Try Another Way')] or descendant::span[contains(normalize-space(),'Need another way to sign in') or contains(normalize-space(),'Need another way to authenticate')])]"
                WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.XPATH, try_another_way_xpath)))
                if not robust_click(driver, wait_medium, By.XPATH, try_another_way_xpath, "Nút 'Try Another Way'"): raise Exception("Ko click 'Try Another Way'")
                time.sleep(1.5)
                radio_2fa_xpath = "//input[@type='radio' and @name='unused' and @value='1']"
                radio_2fa_fallback_xpath = "//div[@role='radiogroup']//div[@role='radio'][descendant::span[contains(lower-case(normalize-space(.)),'authenticator app')]]"
                if not robust_click(driver, wait_medium, By.XPATH, radio_2fa_xpath, "Radio 2FA (value 1)"):
                    if not robust_click(driver, wait_medium, By.XPATH, radio_2fa_fallback_xpath, "Radio 2FA (fallback text)"): raise Exception("Ko click radio 2FA")
                time.sleep(0.5)
                continue_btn_1_xpath = "//div[@role='none' and contains(@class,'x1ja2u2z')][descendant::span[normalize-space(text())='Continue']][not(contains(@class,'xti2d7y'))]"
                continue_btn_1_fallback_xpath = "(//div[@role='button'][descendant::span[normalize-space()='Continue']])[1]"
                if not robust_click(driver, wait_medium, By.XPATH, continue_btn_1_xpath, "Nút 'Continue' sau radio 2FA"):
                    if not robust_click(driver, wait_medium, By.XPATH, continue_btn_1_fallback_xpath, "Nút 'Continue' sau radio 2FA (fallback)"): raise Exception("Ko click Continue sau radio")
                time.sleep(3)
                code_6_digits_taw = get_2fa_code_from_2falive(driver, wait_medium, driver.current_window_handle, two_fa_secret)
                if not code_6_digits_taw: print("Reup: LỖI - Không lấy được mã 2FA (Try Another Way)."); return False
                code_input_xpath_generic = "//input[@type='text'][@autocomplete='off'][@dir='ltr'][not(@name='email')][not(@name='pass')][string-length(@value)=0 or not(@value) or contains(@aria-label,'code') or contains(@id,'approvals_code')]"
                code_input_field_taw = wait_medium.until(EC.visibility_of_element_located((By.XPATH, code_input_xpath_generic)))
                code_input_field_taw.send_keys(code_6_digits_taw); print(f"Reup: Đã điền mã 2FA (TryAnotherWay): {code_6_digits_taw}"); time.sleep(0.5)
                continue_after_code_taw_xpath = "//div[@role='button' or @role='none'][contains(@class,'xti2d7y')][descendant::span[normalize-space()='Continue']]"
                continue_after_code_fallback_taw_xpath = "(//div[@role='button'][descendant::span[normalize-space()='Continue']])[last()]"
                if robust_click(driver, wait_medium, By.XPATH, continue_after_code_taw_xpath, "Nút 'Continue' (xti2d7y) sau mã 2FA (TAW)", timeout=15): print("Reup: Đã nhấn Continue (xti2d7y) sau mã 2FA (TAW)."); time.sleep(3)
                elif robust_click(driver, wait_medium, By.XPATH, continue_after_code_fallback_taw_xpath, "Nút 'Continue' sau mã 2FA (TAW fallback)", timeout=15): print("Reup: Đã nhấn Continue (fallback) sau mã 2FA (TAW)."); time.sleep(3)
                else: raise Exception("Không click được Continue sau khi nhập mã 2FA (TAW)")
                two_fa_flow_completed_successfully = True
            except Exception as e_taw_flow:
                if not two_fa_flow_completed_successfully: print(f"Reup: Không phát hiện/xử lý 2FA 'Try Another Way', hoặc lỗi: {type(e_taw_flow).__name__}")

        current_url_lower = driver.current_url.lower()
        if two_fa_flow_completed_successfully or ("facebook.com" in current_url_lower and not ("checkpoint" in current_url_lower or "login" in current_url_lower or "locked" in current_url_lower)):
            trust_options_xpaths = ["//div[@role='button'][descendant::span[normalize-space()='Save Browser']]", "//div[@role='button'][descendant::span[normalize-space()='Save']]", "//div[@role='button'][descendant::span[normalize-space()='Trust this device']]", "//div[@role='button'][descendant::span[normalize-space()='Yes']]"]
            trusted = any(robust_click(driver, WebDriverWait(driver, 3), By.XPATH, xp, "Nút Trust/Save", timeout=3) for xp in trust_options_xpaths if driver.find_elements(By.XPATH, xp))
            if trusted: print("Reup: Đã click nút Trust/Save."); time.sleep(2)
            try:
                not_now_xpaths = ["//div[@aria-label='Not Now'][@role='button']", "//button[contains(normalize-space(),'Not Now')]", "//a[contains(normalize-space(),'Not Now')]", "//div[@aria-label='Close'][@role='button']", "//button[@aria-label='Close']", "//span[contains(normalize-space(),'Not now')]/ancestor::div[@role='button'][1]", "//div[contains(@class,'autofocus') or contains(@class,'layerCancel')][@role='button']", "//div[@role='dialog']//div[@aria-label='Không phải bây giờ']", "//div[@role='dialog']//button[contains(normalize-space(),'Không phải bây giờ')]"]
                popup_dismissed = any(robust_click(driver, WebDriverWait(driver, 3), By.XPATH, xp, "Nút dismiss pop-up thông báo", timeout=3) for xp in not_now_xpaths if driver.find_elements(By.XPATH, xp))
                if popup_dismissed: print("Reup: Pop-up thông báo đã xử lý."); time.sleep(1.5)
            except Exception as e_noti_pop: print(f"Reup: Lỗi nhỏ khi kiểm tra pop-up thông báo: {e_noti_pop}")
        elif not two_fa_flow_completed_successfully :
             print(f"Reup: LỖI - Vẫn ở trang checkpoint/login ({driver.current_url}) và không hoàn thành luồng 2FA.");
             is_reup_fb_logged_in = False; return False

        target_profile_url = f"https://www.facebook.com/{profile_slug_for_redirect}"
        print(f"Reup: Điều hướng đến profile: {target_profile_url}")
        driver.get(target_profile_url)
        WebDriverWait(driver, 15).until(lambda d: profile_slug_for_redirect.lower() in d.current_url.lower() or EC.presence_of_element_located((By.XPATH, "//div[@aria-label='Tạo bài viết'] | //div[@aria-label='Create post'] | //img[contains(@alt,'profile picture')]"))(d))
        print(f"Reup: Đã ở trang profile {profile_slug_for_redirect} (URL: {driver.current_url})."); time.sleep(2)
        try:
            wait_long.until(EC.any_of(EC.presence_of_element_located((By.XPATH, "//div[@aria-label='Tạo bài viết']")), EC.presence_of_element_located((By.XPATH, "//div[@aria-label='Create post']")), EC.presence_of_element_located((By.XPATH, "//a[@aria-label='Home'] | //a[@aria-label='Trang chủ']")), EC.presence_of_element_located((By.XPATH, f"//a[contains(@href,'{profile_slug_for_redirect}')]//img[contains(@alt,'profile picture')]"))))
            print("Reup: Đăng nhập Facebook và vào profile thành công!"); is_reup_fb_logged_in = True; return True
        except: print(f"Reup: LỖI - Đăng nhập Facebook thất bại hoặc không vào được profile cuối cùng (URL hiện tại: {driver.current_url})."); is_reup_fb_logged_in = False; return False
    except Exception as e_login_main_wrapper:
        print(f"Reup: Lỗi nghiêm trọng khi đăng nhập Facebook: {type(e_login_main_wrapper).__name__} - {e_login_main_wrapper}");
        try: driver.save_screenshot(f"reup_login_error_{time.strftime('%Y%m%d-%H%M%S')}.png")
        except: pass
        is_reup_fb_logged_in = False; return False
    finally:
        if not is_reup_fb_logged_in:
            if driver.current_window_handle == reup_fb_tab_handle and reup_fb_tab_handle in driver.window_handles: driver.close()
            if caller_tab_handle and caller_tab_handle in driver.window_handles: driver.switch_to.window(caller_tab_handle)
            elif driver.window_handles : driver.switch_to.window(driver.window_handles[0])
    return # Should not be reached


def download_image_from_google(driver, wait_medium, wait_long, search_query):
    print(f"   GoogleImg: Tìm ảnh cho '{search_query}'...")
    google_img_tab_original = driver.current_window_handle
    driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
    google_img_tab = driver.window_handles[-1]
    driver.switch_to.window(google_img_tab)
    downloaded_image_path = None
    try:
        encoded_query = quote_plus(search_query)
        Google_Search_url = f"https://www.google.com/search?q={encoded_query}&udm=2&hl=en" # Sửa tên biến ở đây (đã đúng)
        print(f"   GoogleImg: Truy cập URL Google Images...");
        driver.get(Google_Search_url); time.sleep(random.uniform(2.5, 4.0))
        try:
            accept_button_xpaths = ["//button[.//div[contains(text(),'Accept all') or contains(text(),'Accept')]]", "//button[@id='L2AGLb']", "//div[@role='button'][contains(normalize-space(.),'Accept all')]", "//button[contains(normalize-space(.),'Accept all')]"]
            cookie_accepted = any(robust_click(driver, WebDriverWait(driver,3), By.XPATH, xp, "Nút Accept Cookies Google", timeout=3) for xp in accept_button_xpaths if driver.find_elements(By.XPATH, xp))
            if cookie_accepted: print("   GoogleImg: Đã chấp nhận cookies."); time.sleep(random.uniform(1.0, 2.0))
        except Exception as e_cookie: print(f"   GoogleImg: Bỏ qua cookies (lỗi hoặc không có): {e_cookie}")

        print("   GoogleImg: Tìm và click thumbnail ảnh đầu tiên...")
        first_image_container_xpath = "(//div[contains(@class,'isv-r') or contains(@class,'Q4LuWd') or contains(@class,'mVDgc')]//a[.//img[@alt and not(contains(@src,'data:image')) and not(contains(@style,'display:none'))]])[1]"
        first_image_container_fallback_xpath = "(//a[.//img[@alt and string-length(@alt)>0 and not(contains(@src,'data:image'))]])[position()>=1 and position()<=5]"
        thumbnail_container = None
        try: thumbnail_container = wait_long.until(EC.element_to_be_clickable((By.XPATH, first_image_container_xpath)))
        except:
            try:
                candidates = driver.find_elements(By.XPATH, first_image_container_fallback_xpath)
                if candidates: thumbnail_container = candidates[random.randint(0, min(len(candidates)-1, 2))]
            except Exception as e_thumb_fallback: print(f"   GoogleImg: Lỗi tìm thumbnail fallback: {e_thumb_fallback}")

        if thumbnail_container:
            thumbnail_container.click(); print("   GoogleImg: Đã click thumbnail. Chờ panel preview (4s)..."); time.sleep(4)
        else:
            print("   GoogleImg: LỖI - Không tìm thấy thumbnail ảnh đầu tiên để click.");
            if driver.current_window_handle == google_img_tab and google_img_tab in driver.window_handles : driver.close()
            if google_img_tab_original in driver.window_handles: driver.switch_to.window(google_img_tab_original)
            return None

        full_image_url = None
        possible_large_image_xpaths = [
            "//div[@role='dialog' or @id='islsp' or contains(@jsname,'lightbox') or contains(@class,'ivg-i') or contains(@class,'ZFyM1d')]//img[@src[starts-with(.,'http') and not(contains(.,'gstatic.com')) and not(contains(.,'google.com/images')) and string-length(@src)>100]][not(contains(@style,'display: none')) and not(contains(@style,'visibility:hidden'))][1]",
            "//img[@class='sFlh5c pT0Scc iPVvYb']", "//img[@jsname='Q4LuWd'][@src[starts-with(.,'http')]]",
            "//div[@id='Sva75c']//div[@data-a4b']//img[@src[starts-with(.,'http')]]",
            "//img[contains(@class,'n3VNCb') and @src[starts-with(.,'http')]]"
        ]
        img_candidates = []
        for i, xpath_full in enumerate(possible_large_image_xpaths):
            try:
                image_elements = WebDriverWait(driver, random.uniform(2,4)).until(EC.presence_of_all_elements_located((By.XPATH, xpath_full)))
                for img_el in image_elements:
                    if img_el.is_displayed():
                        src = img_el.get_attribute('src') or img_el.get_attribute('data-src')
                        if src and src.startswith('http') and not src.startswith('data:image') and len(src)>50:
                            try:
                                w = int(img_el.get_attribute("naturalWidth") or img_el.size.get('width',0))
                                h = int(img_el.get_attribute("naturalHeight") or img_el.size.get('height',0))
                                img_candidates.append({'url': src, 'width': w, 'height': h, 'area': w * h })
                            except: img_candidates.append({'url': src, 'width': 0, 'height': 0, 'area': 0 })
            except: continue
        if img_candidates:
            img_candidates.sort(key=lambda x: x['area'], reverse=True)
            for candidate in img_candidates:
                if candidate['width'] >= 480 and candidate['height'] >= 360: 
                    full_image_url = candidate['url']; break
            if not full_image_url and img_candidates: full_image_url = img_candidates[0]['url']

        if full_image_url:
            print(f"   GoogleImg: Tìm thấy URL ảnh: {full_image_url}")
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
                img_response = requests.get(full_image_url, timeout=25, headers=headers, stream=True, allow_redirects=True)
                img_response.raise_for_status(); img_data = img_response.content
                if not os.path.exists(PHOTOS_DOWNLOAD_FOLDER): os.makedirs(PHOTOS_DOWNLOAD_FOLDER)
                safe_query_part = re.sub(r'[^a-zA-Z0-9_-]', '_', search_query[:30])
                temp_image_filename = f"gimg_{safe_query_part}_{int(time.time())}.jpg"
                content_type = img_response.headers.get('content-type')
                if content_type:
                    if 'png' in content_type: temp_image_filename = temp_image_filename.replace(".jpg",".png")
                    elif 'gif' in content_type: temp_image_filename = temp_image_filename.replace(".jpg",".gif")
                    elif 'webp' in content_type: temp_image_filename = temp_image_filename.replace(".jpg",".webp")
                downloaded_image_path = os.path.join(PHOTOS_DOWNLOAD_FOLDER, temp_image_filename)
                with open(downloaded_image_path, 'wb') as handler: handler.write(img_data)
                print(f"   GoogleImg: Đã tải ảnh về: {downloaded_image_path}")
            except Exception as e_download: print(f"   GoogleImg: Lỗi khi tải/lưu ảnh: {e_download}"); downloaded_image_path = None
        else:
            print("   GoogleImg: Không lấy được URL ảnh đầy đủ hợp lệ.");
            try: driver.save_screenshot(f"gimg_no_url_error_{time.strftime('%Y%m%d-%H%M%S')}.png")
            except: pass
    except Exception as e_gimg:
        print(f"   GoogleImg: Lỗi chung Google Images: {type(e_gimg).__name__} - {e_gimg}")
        try: driver.save_screenshot(f"gimg_general_error_{time.strftime('%Y%m%d-%H%M%S')}.png")
        except: pass
    finally:
        if driver.current_window_handle == google_img_tab and google_img_tab in driver.window_handles: driver.close()
        if google_img_tab_original in driver.window_handles: driver.switch_to.window(google_img_tab_original)
        elif driver.window_handles: driver.switch_to.window(driver.window_handles[0])
    return downloaded_image_path


def create_facebook_post_on_reup_tab(driver, wait_medium, wait_long, reup_profile_slug, uspto_wordmark_for_post):
    global reup_fb_tab_handle, is_reup_fb_logged_in
    if not is_reup_fb_logged_in or not reup_fb_tab_handle or reup_fb_tab_handle not in driver.window_handles:
        print("ReupPost: Chưa đăng nhập hoặc tab reup không hợp lệ."); return None

    original_tab_before_post = driver.current_window_handle
    if driver.current_window_handle != reup_fb_tab_handle: driver.switch_to.window(reup_fb_tab_handle)
    print("\nReupPost: Đang ở tab Reup để đăng bài...")
    post_link = None
    downloaded_image_for_this_post = None
    try:
        profile_page_url = f"https://www.facebook.com/{reup_profile_slug}"
        if not (reup_profile_slug.lower() in driver.current_url.lower() and "facebook.com" in driver.current_url.lower()):
            print(f"ReupPost: Điều hướng đến trang cá nhân: {profile_page_url}")
            driver.get(profile_page_url)
            try: WebDriverWait(driver, 15).until(EC.url_contains(reup_profile_slug.lower()))
            except: WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[@aria-label='Tạo bài viết'] | //div[@aria-label='Create post'] | //div[@role='main']")))
            time.sleep(3)
        print(f"ReupPost: Đã ở trang profile ({driver.current_url}).")
        check_and_close_cover_photo_error(driver, "AfterProfileNav_Reup")

        downloaded_image_for_this_post = download_image_from_google(driver, wait_medium, wait_long, uspto_wordmark_for_post)
        if driver.current_window_handle != reup_fb_tab_handle:
            if reup_fb_tab_handle in driver.window_handles:
                driver.switch_to.window(reup_fb_tab_handle); print("ReupPost: Đã chuyển lại tab Reup FB sau khi tải ảnh Google.")
            else: print("ReupPost: LỖI - Tab Reup FB không còn tồn tại sau khi tải ảnh Google."); return None
        check_and_close_cover_photo_error(driver, "AfterGoogleImage_Reup")

        print("ReupPost: Click nút 'Photo/video' trực tiếp trên trang...")
        direct_photo_video_button_xpath = "//div[@role='button'][.//span[normalize-space(text())='Photo/video']][.//img[contains(@src, 'rsrc.php') or contains(@data-imgperflogname,'media_photo')]]"
        direct_photo_video_button_fallback_xpath = "//div[@role='button'][@aria-label='Photo/video' or @aria-label='Ảnh/video' or contains(@aria-label,'Create a new post with a photo or video')]"
        user_specific_class_pv_button_xpath = "//div[contains(@class, 'x1i10hfl') and contains(@class, 'xurb0ha') and @role='button'][.//span[normalize-space(text())='Photo/video']]"
        clicked_initial_pv_button = False
        if robust_click(driver, wait_medium, By.XPATH, direct_photo_video_button_xpath, "Nút 'Photo/video' trực tiếp (có img)"): clicked_initial_pv_button = True
        elif robust_click(driver, wait_medium, By.XPATH, direct_photo_video_button_fallback_xpath, "Nút 'Photo/video' trực tiếp (aria-label)"): clicked_initial_pv_button = True
        elif robust_click(driver, wait_medium, By.XPATH, user_specific_class_pv_button_xpath, "Nút 'Photo/video' trực tiếp (user class)"): clicked_initial_pv_button = True
        else: print("ReupPost: LỖI - Không click được nút 'Photo/video' trực tiếp trên trang."); return None
        print("ReupPost: Đã click nút 'Photo/video' trực tiếp. Chờ dialog (5s)..."); time.sleep(5)

        check_and_close_cover_photo_error(driver, "AfterInitialPhotoVideoClick_Reup")

        print("ReupPost: Click 'Add photos/videos' trong dialog...")
        add_photos_videos_in_dialog_user_xpath = "//div[contains(@class,'x9f619') and contains(@class,'x1n2onr6') and .//span[normalize-space()='Add photos/videos'] and .//i[contains(@style,'Vq2Ahx_cetr.png')]]"
        add_photos_videos_in_dialog_fallback_xpath = "//div[@role='dialog' or contains(@aria-label,'Create post') or contains(@aria-label,'Tạo bài viết')]//div[@role='button'][.//span[normalize-space(text())='Add photos/videos'] or .//div[normalize-space(text())='Add Photos/Videos']]"
        add_photos_videos_in_dialog_text_only_xpath = "//div[@role='dialog']//span[normalize-space(text())='Add photos/videos']/ancestor::div[@role='button'][1]"
        clicked_add_pv_in_dialog = False
        if robust_click(driver, wait_medium, By.XPATH, add_photos_videos_in_dialog_user_xpath, "Nút 'Add photos/videos' trong dialog (user HTML)"): clicked_add_pv_in_dialog = True
        elif robust_click(driver, wait_medium, By.XPATH, add_photos_videos_in_dialog_fallback_xpath, "Nút 'Add photos/videos' trong dialog (fallback)"): clicked_add_pv_in_dialog = True
        elif robust_click(driver, wait_medium, By.XPATH, add_photos_videos_in_dialog_text_only_xpath, "Nút 'Add photos/videos' trong dialog (text only)"): clicked_add_pv_in_dialog = True
        if not clicked_add_pv_in_dialog:
            print("ReupPost: LỖI - Không click được 'Add photos/videos' trong dialog.")
            if not downloaded_image_for_this_post: print("ReupPost: Sẽ thử đăng text nếu không có ảnh.")
            else: return None
        else:
            print("ReupPost: Đã click 'Add photos/videos'. Chờ input file (3s)..."); time.sleep(3)
            check_and_close_cover_photo_error(driver, "AfterAddPhotosVideosClick_Reup")

            if downloaded_image_for_this_post and os.path.exists(downloaded_image_for_this_post):
                print(f"ReupPost: Upload ảnh '{downloaded_image_for_this_post}'...")
                try:
                    file_input_xpath = "//input[@type='file'][@accept and (contains(@accept,'image/*') or contains(@accept,'video/*'))][not(ancestor::div[contains(@style,'display: none')])]"
                    file_input_element = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, file_input_xpath)))
                    file_input_element.send_keys(os.path.abspath(downloaded_image_for_this_post))
                    print(f"ReupPost: Đã gửi đường dẫn ảnh. Chờ upload và xử lý (35s)..."); time.sleep(35)
                    print("ReupPost: Đã chờ upload ảnh.")
                    check_and_close_cover_photo_error(driver, "AfterImageUploadAttempt_Reup")
                except Exception as e_photo_upload: print(f"ReupPost: Lỗi khi upload ảnh bằng send_keys: {e_photo_upload}.")
            elif downloaded_image_for_this_post : print(f"ReupPost: Ảnh tải về '{downloaded_image_for_this_post}' không tồn tại.")
            else: print("ReupPost: Không có ảnh từ Google để upload.")

        post_text_content = f"Reviewing: {uspto_wordmark_for_post}"
        print(f"ReupPost: Điền caption: '{post_text_content}'")
        check_and_close_cover_photo_error(driver, "BeforeCaptionFill_Reup")
        caption_editor_xpaths = [
            "//div[contains(@aria-label,'Tạo bài viết') or contains(@aria-label,'Create a post') or contains(@aria-label,'Soạn bài viết') or contains(@aria-label,'What are you thinking')]//div[@role='textbox'][@contenteditable='true']",
            "//div[@data-lexical-editor='true']//div[@contenteditable='true']",
            "//div[@aria-describedby and @role='textbox']", "//textarea[@placeholder=\"What's on your mind?\"]",
            "//div[@role='combobox'][@contenteditable='true']"
        ]
        caption_filled = False
        for xp_caption in caption_editor_xpaths:
            try:
                caption_area_container = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xp_caption)))
                caption_area = caption_area_container.find_element(By.XPATH, ".//div[@role='textbox'][@contenteditable='true']") if caption_area_container.get_attribute("role") != "textbox" and caption_area_container.get_attribute("contenteditable") != "true" else caption_area_container
                try: driver.execute_script("arguments[0].click();", caption_area); time.sleep(0.3)
                except: caption_area.click(); time.sleep(0.3)
                caption_area.send_keys(Keys.CONTROL + "a"); time.sleep(0.1); caption_area.send_keys(Keys.DELETE); time.sleep(0.1)
                caption_area.send_keys(post_text_content)
                caption_filled = True; print("   ReupPost: Đã điền caption."); break
            except: continue
        if not caption_filled: print("   ReupPost: CẢNH BÁO - Không tìm thấy ô để điền caption.")
        time.sleep(1)

        print("ReupPost: Click nút 'Next' (nếu có)...")
        check_and_close_cover_photo_error(driver, "BeforeNextButton_Reup")
        next_button_xpath_user = "//div[@aria-label='Next'][@role='button'][contains(@class,'x1i10hfl') or contains(@class,'xqv03lk')]"
        try:
            if robust_click(driver, WebDriverWait(driver, 7), By.XPATH, next_button_xpath_user, "Nút 'Next'", timeout=7): print("ReupPost: Đã click nút 'Next'."); time.sleep(2)
        except: pass

        print("ReupPost: Click nút Post cuối cùng...")
        check_and_close_cover_photo_error(driver, "BeforeFinalPost_Reup")
        final_post_button_xpaths = [
            "//div[@aria-label='Post'][@role='button'][contains(@class,'x1i10hfl') or contains(@class,'xqv03lk')][not(@aria-disabled='true')]",
            "//div[@role='button'][descendant::span[normalize-space(.)='Post']][not(@aria-disabled='true')]",
            "//button[@type='submit'][normalize-space(.)='Post'][not(@disabled)]"
        ]
        posted_successfully = any(robust_click(driver, wait_medium, By.XPATH, xp_post, f"Nút Post cuối cùng (thử)") for xp_post in final_post_button_xpaths)
        if not posted_successfully: print("ReupPost: LỖI - Không thể click nút Post."); return None
        print("ReupPost: Đã click nút Post.");

        print("ReupPost: Reload ngay sau khi nhấn Post..."); driver.refresh()
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")));
        try: WebDriverWait(driver, 20).until(EC.any_of(EC.presence_of_element_located((By.XPATH, "//div[@role='feed']")), EC.presence_of_element_located((By.XPATH, f"//a[contains(@href,'{reup_profile_slug}')]"))))
        except: print("ReupPost: Không thấy feed/link profile sau reload.")
        time.sleep(random.uniform(7.0, 10.0))
        print("ReupPost: Đã reload. Tìm link bài đăng...")
        post_link = None
        ts_xpaths_priority = [
            "(//div[@role='article'][1]//span[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ','abcdefghijklmnopqrstuvwxyzàáâãèéêìíòóôõùúýđ'),'vừa xong') or contains(translate(normalize-space(.),'JMN','jmn'),'just now') or contains(normalize-space(.),' giây') or contains(normalize-space(.),' second')]/ancestor::a[@href and (contains(@href,'/posts/') or contains(@href,'/permalink/') or contains(@href,'fbid=') or contains(@href,'/videos/') or contains(@href,'/photos/') or contains(@href, '/watch/'))])[1]",
            "(//div[@role='article'][1]//a[contains(@href,'/posts/') or contains(@href,'/permalink/')][.//span[contains(lower-case(normalize-space(.)),'just now') or contains(lower-case(normalize-space(.)),'phút') or contains(lower-case(normalize-space(.)),'giờ') or contains(lower-case(normalize-space(.)),'vừa xong')]])[1]"
        ]
        for i, xp in enumerate(ts_xpaths_priority):
            try:
                link_el = WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.XPATH, xp)))
                post_link = link_el.get_attribute("href")
                if post_link and "facebook.com" in post_link: print(f"ReupPost: Link từ timestamp/aria-label (thử {i+1}): {post_link}"); break
                else: post_link = None
            except: post_link = None
       
        if not post_link or "facebook.com" not in post_link:
            posted_content_link_xpath_user = "(//div[@role='article'][1]//a[contains(@href,'/photo/?fbid=') or contains(@href,'/photos/') or contains(@href,'/videos/') or contains(@href,'/video/')])[1]"
            try:
                link_to_click_for_url = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, posted_content_link_xpath_user)))
                potential_href = link_to_click_for_url.get_attribute("href")
                if robust_click(driver, WebDriverWait(driver,10), By.XPATH, posted_content_link_xpath_user, "Link/Ảnh của bài đăng mới nhất"):
                    time.sleep(4); current_url_after_click = driver.current_url
                    if any(s in current_url_after_click for s in ["facebook.com/photo.php", "facebook.com/photos/", "facebook.com/video"]): post_link = current_url_after_click; print(f"ReupPost: URL sau khi click nội dung: {post_link}")
                    elif potential_href and "facebook.com" in potential_href: post_link = potential_href; print(f"ReupPost: URL sau click không rõ ràng, dùng href: {post_link}")
                elif potential_href and "facebook.com" in potential_href: post_link = potential_href; print("ReupPost: Click vào nội dung thất bại, dùng href: {post_link}")
            except Exception as e_click_img_link: print(f"ReupPost: Lỗi khi click vào link ảnh/bài đăng: {type(e_click_img_link).__name__}")

        if not post_link or "facebook.com" not in post_link :
            print("ReupPost: LỖI - Không lấy được link bài đăng cụ thể. Dùng URL profile hiện tại.");
            post_link = driver.current_url
        print(f"ReupPost: Hoàn tất, link sẽ sử dụng: {post_link}")

    except Exception as e_reup_posting:
        print(f"ReupPost: Lỗi trong quy trình đăng bài: {type(e_reup_posting).__name__} - {e_reup_posting}")
        try: driver.save_screenshot(f"reup_posting_error_{time.strftime('%Y%m%d-%H%M%S')}.png")
        except: pass
        if not post_link: post_link = f"https://www.facebook.com/{reup_profile_slug}"; print(f"ReupPost: Do lỗi, sử dụng link profile mặc định: {post_link}")
    finally:
        if downloaded_image_for_this_post and os.path.exists(downloaded_image_for_this_post):
            try: os.remove(downloaded_image_for_this_post);
            except Exception as e_del: print(f"   ReupPost: Lỗi khi xóa ảnh tạm {downloaded_image_for_this_post}: {e_del}")
    if driver.current_window_handle != original_tab_before_post and original_tab_before_post in driver.window_handles: driver.switch_to.window(original_tab_before_post)
    return post_link

def fill_trademark_form_and_verify_email(driver, wait_medium, wait_long, uspto_owners_name, current_email_info_dict, website_for_tm_form, uspto_wordmark_for_tm_form, uspto_serial_for_tm_form, reup_post_link_for_tm_form, all_additional_info_lines):
    # ... (Nội dung hàm giữ nguyên) ...
    trademark_form_email_address = current_email_info_dict['email']
    webmail_password = current_email_info_dict['password']
    email_use_count = current_email_info_dict['use_count']
    stored_verification_code = current_email_info_dict['last_code']
    form_submission_successful = False
    print("\n   TM Form: Mở tab mới...")
    original_tab_before_tm_form = driver.current_window_handle
    driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
    tm_form_tab_handle = driver.window_handles[-1]
    important_tabs = {original_tab_before_tm_form}
    if reup_fb_tab_handle: important_tabs.add(reup_fb_tab_handle)
    if hasattr(main, 'initial_main_tab') and main.initial_main_tab: important_tabs.add(main.initial_main_tab)
    if tm_form_tab_handle in important_tabs:
        temp_tabs_before_tm = set(driver.window_handles)
        driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
        newly_opened_tm_tabs = [h for h in driver.window_handles if h not in temp_tabs_before_tm]
        if not newly_opened_tm_tabs: print("   TM Form: LỖI - Vẫn không thể mở tab mới an toàn."); return False
        tm_form_tab_handle = newly_opened_tm_tabs[0]

    driver.switch_to.window(tm_form_tab_handle)
    try:
        driver.get(URL_FACEBOOK_TRADEMARK_FORM); print(f"   TM Form: Đã mở URL."); time.sleep(1.5)
        if not robust_click(driver, wait_medium, By.XPATH, "//label[normalize-space(text())='Continue with my trademark report']", "Label 'Continue report'"):
            if not robust_click(driver, wait_medium, By.XPATH, "//input[@name='continuereport' and @value='trademark']", "Input 'Continue report'"): raise Exception("Ko click 'Continue report'")
        time.sleep(2)
        wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@id,'SupportFormRow') and .//input[@name='relationship_rightsowner']]")))
        if not robust_click(driver, wait_medium, By.XPATH, "//label[normalize-space(text())='I am the rights owner']", "Label 'I am rights owner'"):
            if not robust_click(driver, wait_medium, By.XPATH, "//input[@name='relationship_rightsowner' and @value='I am the rights owner']", "Input 'I am rights owner'"): raise Exception("Ko click 'I am rights owner'")
        time.sleep(2)
        name_to_use = uspto_owners_name if uspto_owners_name else "Trademark Holder"
        for name_attr_val in ['your_name', 'reporter_name', 'signature']:
            el = wait_medium.until(EC.visibility_of_element_located((By.XPATH, f"//input[@name='{name_attr_val}']"))); el.clear(); el.send_keys(name_to_use)
        addr = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//textarea[@name='Address']"))); addr.clear(); addr.send_keys(FB_FORM_POSTAL_ADDRESS)
        if trademark_form_email_address:
            em1 = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='email']"))); em1.clear(); em1.send_keys(trademark_form_email_address)
            em2 = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='confirm_email']"))); em2.clear(); em2.send_keys(trademark_form_email_address)
        if website_for_tm_form:
            web_f = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='websiterightsholder']"))); web_f.clear(); web_f.send_keys(website_for_tm_form)
        if uspto_wordmark_for_tm_form:
            tm_fld = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='what_is_your_trademark']"))); tm_fld.clear(); tm_fld.send_keys(uspto_wordmark_for_tm_form); tm_fld.send_keys(Keys.TAB); time.sleep(2)
        
        country_dd_xpath = "//div[@id='SupportFormRow.3411356655770500']//select[@name='rights_owner_country_routing']"
        country_dd_fallback_xpath = "//select[@name='rights_owner_country_routing']"
        country_dd = None
        try: country_dd = wait_medium.until(EC.element_to_be_clickable((By.XPATH, country_dd_xpath)))
        except: country_dd = wait_medium.until(EC.element_to_be_clickable((By.XPATH, country_dd_fallback_xpath)))
        if country_dd and country_dd.is_enabled(): Select(country_dd).select_by_value(FB_FORM_TRADEMARK_REG_COUNTRY);
        time.sleep(1)

        if uspto_serial_for_tm_form:
            tm_url_ta = wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//div[@id='SupportFormRow.332711233753465']//textarea[@name='TM_URL'] | //textarea[@name='TM_URL']")))
            tm_url_ta.clear(); tm_url_ta.send_keys(uspto_serial_for_tm_form); time.sleep(1)

        parent_div_ct_xpath = "//div[@id='SupportFormRow.1112475925434379']"
        label_inf_xpath = f"{parent_div_ct_xpath}//label[normalize-space(text())=\"This photo, video, post, story or ad uses the rights owner's trademark\"]"
        label_inf_fallback_xpath = "//label[contains(normalize-space(.),'This photo, video, post, story or ad uses the rights owner')]/preceding-sibling::input[@type='checkbox'] | //input[@type='checkbox'][following-sibling::label[contains(normalize-space(.),'This photo, video, post, story or ad uses the rights owner')]]"
        clicked_reason = False
        if robust_click(driver, wait_medium, By.XPATH, label_inf_xpath, "Label lý do vi phạm"): clicked_reason = True
        elif robust_click(driver, wait_medium, By.XPATH, label_inf_fallback_xpath, "Checkbox lý do vi phạm (fallback)"): clicked_reason = True
        else:
             input_reason_val_xpath = f"{parent_div_ct_xpath}//input[@name='content_type[]' and @value=\"This photo, video, post, story or ad uses the rights owner's trademark\"]"
             if robust_click(driver, wait_medium, By.XPATH, input_reason_val_xpath, "Input lý do vi phạm (value)"): clicked_reason = True
        if clicked_reason: print("   TM Form: Đã tích checkbox lý do vi phạm."); time.sleep(1)
        else: print("   TM Form: CẢNH BÁO - Không tích được checkbox lý do vi phạm.")

        if reup_post_link_for_tm_form:
            content_urls_ta_xpath = "//div[@id='SupportFormRow.1622541521292980']//textarea[@name='content_urls'] | //textarea[@name='content_urls']"
            content_urls_ta = wait_medium.until(EC.visibility_of_element_located((By.XPATH, content_urls_ta_xpath)))
            content_urls_ta.clear(); content_urls_ta.send_keys(reup_post_link_for_tm_form); time.sleep(0.5)
        if all_additional_info_lines:
            random_info = random.choice(all_additional_info_lines)
            add_info_ta_xpath = "//textarea[@name='additionalinfo' and (@id='125859267561673' or @data-testid='SupportFormTextArea-additionalinfo')]"
            add_info_ta = wait_medium.until(EC.visibility_of_element_located((By.XPATH, add_info_ta_xpath)))
            add_info_ta.clear(); add_info_ta.send_keys(random_info); time.sleep(0.5)

        submit_button_xpath = "//button[@type='submit'][normalize-space()='Submit' or contains(@class, '_51sy') or normalize-space()='Send']"
        if not robust_click(driver, wait_medium, By.XPATH, submit_button_xpath, "Nút Submit Form"): raise Exception("Ko click Submit Form")
        print("   TM Form: Đã Submit. Chờ trang nonce hoặc xác nhận (10s)..."); time.sleep(10)
        nonce_input_present = False
        try:
            WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.XPATH, "//input[@name='nonce' and contains(@placeholder,'Submit your code')]")))
            nonce_input_present = True
        except:
            try:
                WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'thank you for your report') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'your report has been submitted')]")))
                print("   TM Form: Báo cáo thành công mà không cần mã nonce.")
                form_submission_successful = True; return form_submission_successful
            except: print("   TM Form: Không có nonce và cũng không có thông báo thành công rõ ràng.")

        final_code_to_use = stored_verification_code if email_use_count > 0 and stored_verification_code and nonce_input_present else None
        if not final_code_to_use and nonce_input_present:
            print(f"   EmailVerify: Lần {email_use_count + 1} cho '{trademark_form_email_address}'. Chờ email (60s)..."); time.sleep(60)
            original_tabs_wm = set(driver.window_handles); driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
            webmail_tab = next((h for h in driver.window_handles if h not in original_tabs_wm), None)
            if not webmail_tab: print("   EmailVerify: Lỗi mở tab webmail."); return False
            driver.switch_to.window(webmail_tab); driver.get(URL_WEBMAIL)
            try:
                wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='user']"))).send_keys(trademark_form_email_address)
                wait_medium.until(EC.visibility_of_element_located((By.XPATH, "//input[@name='pass']"))).send_keys(webmail_password)
                if not robust_click(driver, wait_medium, By.XPATH, "//button[@id='login_submit']", "Login Webmail"): raise Exception("Ko login webmail")
                time.sleep(5)
                try:
                    if robust_click(driver, WebDriverWait(driver, 7), By.XPATH, "//button[@id='btnSaveAndContinue']", "Save&Continue Webmail"): time.sleep(3)
                except: pass
                if not robust_click(driver, wait_medium, By.XPATH, "//button[@id='launchActiveButton']", "Open Webmail"): raise Exception("Ko click Open webmail")
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "messagelistcontainer")))
                time.sleep(5)
                first_email_xpath = "(//table[@id='messagelist']/tbody/tr[contains(@class,'message') and not(contains(@class,'deleted'))])[1]"
                WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, first_email_xpath))).click()
                time.sleep(10)
                wait_long.until(EC.any_of(EC.presence_of_element_located((By.ID, 'messagecontframe')), EC.presence_of_element_located((By.XPATH, "//div[@id='message-htmlpart1'][.//*[contains(@class,'v1mb_text')]]")))); time.sleep(3)
                newly_fetched_code_for_fb = ""
                email_body_code_user_xpath = "//div[@id='message-htmlpart1']//table//span[@class='v1mb_text'][string-length(normalize-space(text()))=6][translate(normalize-space(text()), '0123456789', '')='']"
                email_body_code_general_xpath = "//div[@id='message-htmlpart1']//*[contains(text(),'Facebook') or contains(text(),'code')]/ancestor::table[1]//span[string-length(normalize-space(text()))=6][translate(normalize-space(text()),'0123456789','') = ''] | //div[@id='message-htmlpart1']//*[string-length(normalize-space(text()))=6][translate(normalize-space(text()),'0123456789','') = '']"
                code_elements = []
                try:
                    iframe = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//iframe[@id='messagecontframe' or @id='messageBody' or @name='messagecontframe']")))
                    driver.switch_to.frame(iframe);
                    try: code_elements = driver.find_elements(By.XPATH, email_body_code_user_xpath)
                    except: pass
                    if not code_elements: code_elements = driver.find_elements(By.XPATH, email_body_code_general_xpath)
                    driver.switch_to.default_content();
                except:
                    driver.switch_to.default_content()
                    try: code_elements = driver.find_elements(By.XPATH, email_body_code_user_xpath)
                    except: pass
                    if not code_elements: code_elements = driver.find_elements(By.XPATH, email_body_code_general_xpath)
                if code_elements:
                    newly_fetched_code_for_fb = code_elements[-1].text.strip()
                    print(f"   Webmail: Tìm thấy mã: {newly_fetched_code_for_fb}")
                    current_email_info_dict['last_code'] = newly_fetched_code_for_fb
                    final_code_to_use = newly_fetched_code_for_fb
                else: print("   Webmail: Không tìm thấy mã code 6 số trong email.")
            except Exception as e_wm: print(f"   Webmail: Lỗi xử lý webmail: {e_wm}")
            finally:
                if driver.current_window_handle == webmail_tab and webmail_tab in driver.window_handles: driver.close()
                if tm_form_tab_handle in driver.window_handles: driver.switch_to.window(tm_form_tab_handle)
                else: print("LỖI: Tab TM form đã bị đóng."); return False
        
        if nonce_input_present:
            if not final_code_to_use: print("   EmailVerify: LỖI - Không có mã để điền."); form_submission_successful = False
            else:
                print(f"   EmailVerify: Điền mã '{final_code_to_use}'...")
                nonce_input_xpath = "//input[@name='nonce' and contains(@placeholder,'Submit your code')]"
                confirm_btn_xpath = "//button[@type='submit'][normalize-space()='Confirm'][contains(@class,'layerConfirm') or contains(@class,'_51sy')]"
                try:
                    wait_medium.until(EC.visibility_of_element_located((By.XPATH, nonce_input_xpath))).send_keys(final_code_to_use)
                    if robust_click(driver, wait_medium, By.XPATH, confirm_btn_xpath, "Nút Confirm Nonce"):
                        print("   EmailVerify: Đã Confirm. Chờ xác nhận cuối cùng (10s)..."); time.sleep(10)
                        WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'thank you for your report') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'your report has been submitted')]")))
                        print("   TM Form: Báo cáo thành công SAU KHI nhập mã nonce.")
                        form_submission_successful = True
                    else: print("   EmailVerify: LỖI - Ko click đc Confirm Nonce."); form_submission_successful = False
                except Exception as e_n: print(f"   EmailVerify: LỖI nonce: {e_n}"); form_submission_successful = False
    except Exception as e_tm_main: print(f"   TM Form: LỖI CHUNG: {type(e_tm_main).__name__} - {e_tm_main}"); return False
    finally:
        if driver.current_window_handle == tm_form_tab_handle and tm_form_tab_handle in driver.window_handles: driver.close()
        if original_tab_before_tm_form in driver.window_handles: driver.switch_to.window(original_tab_before_tm_form)
        elif reup_fb_tab_handle and reup_fb_tab_handle in driver.window_handles: driver.switch_to.window(reup_fb_tab_handle)
        elif hasattr(main, 'initial_main_tab') and main.initial_main_tab and main.initial_main_tab in driver.window_handles : driver.switch_to.window(main.initial_main_tab)
        elif driver.window_handles: driver.switch_to.window(driver.window_handles[0])
    return form_submission_successful

def main():
    driver = configure_main_driver()
    if not driver: print("Không thể khởi tạo WebDriver. Thoát."); return

    reup_username_email, reup_password, reup_2fa_secret, reup_profile_slug = "", "", "", ""
    if os.path.exists(REUP_ACCOUNT_FILE):
        try:
            with open(REUP_ACCOUNT_FILE, "r", encoding="utf-8") as f_reup: first_line = f_reup.readline().strip()
            if first_line:
                parts = first_line.split('|');
                if len(parts) >= 3:
                    reup_username_email, reup_password, reup_2fa_secret = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    reup_profile_slug = parts[3].strip() if len(parts) >= 4 and parts[3].strip() else (reup_username_email.split('@')[0] if '@' in reup_username_email else reup_username_email)
                    print(f"Đã đọc thông tin reup: User='{reup_username_email}', Slug='{reup_profile_slug}'")
                else: print(f"Lỗi: Dòng '{REUP_ACCOUNT_FILE}' không đủ 3 phần."); driver.quit(); return
            else: print(f"Lỗi: File '{REUP_ACCOUNT_FILE}' rỗng."); driver.quit(); return
        except Exception as e: print(f"Lỗi đọc '{REUP_ACCOUNT_FILE}': {e}"); driver.quit(); return
    else: print(f"Lỗi: Không tìm thấy '{REUP_ACCOUNT_FILE}'."); driver.quit(); return

    email_data_list = []
    if os.path.exists(EMAIL_DATA_FILE):
        try:
            with open(EMAIL_DATA_FILE, "r", encoding="utf-8") as f_email:
                for line in f_email:
                    line = line.strip()
                    if line and '|' in line:
                        email_part, pass_part = line.split('|', 1)
                        email_data_list.append({'email': email_part.strip(), 'password': pass_part.strip(), 'use_count': 0, 'last_code': None})
            if not email_data_list: print(f"Cảnh báo: '{EMAIL_DATA_FILE}' rỗng hoặc sai định dạng.")
            else: print(f"Đã đọc {len(email_data_list)} email/pass từ '{EMAIL_DATA_FILE}'.")
        except Exception as e: print(f"Lỗi khi đọc '{EMAIL_DATA_FILE}': {e}")
    if not email_data_list: print("LỖI: Cần dữ liệu email để chạy."); driver.quit(); return
    current_email_data_idx = 0
    
    uspto_search_items = []
    if os.path.exists(LIST_FILE_INPUT):
        with open(LIST_FILE_INPUT, "r", encoding="utf-8") as f_list: uspto_search_items = [ln.strip() for ln in f_list if ln.strip()]
    if not uspto_search_items: print(f"Lỗi: '{LIST_FILE_INPUT}' rỗng."); driver.quit(); return
    print(f"Đã đọc {len(uspto_search_items)} mục từ '{LIST_FILE_INPUT}'.")

    additional_info_lines = []
    if os.path.exists(ADDITIONAL_INFO_FILE):
        with open(ADDITIONAL_INFO_FILE, "r", encoding="utf-8") as f_form_txt:
            additional_info_lines = [line.strip() for line in f_form_txt if line.strip()]
        if additional_info_lines: print(f"Đã đọc {len(additional_info_lines)} dòng từ '{ADDITIONAL_INFO_FILE}'.")
    
    main.initial_main_tab = driver.current_window_handle
    if not main.initial_main_tab: print("LỖI: WebDriver không có window handle ban đầu."); driver.quit(); return
    
    if not execute_facebook_reup_login_once(driver, WebDriverWait(driver,20), WebDriverWait(driver,45), 
                                            reup_username_email, reup_password, reup_2fa_secret, reup_profile_slug):
        print("LỖI NGHIÊM TRỌNG: Không thể đăng nhập tài khoản Reup Facebook. Dừng script.")
        driver.quit(); return
    
    if driver.current_window_handle == reup_fb_tab_handle and reup_fb_tab_handle is not None and len(driver.window_handles) > 1:
        other_tabs = [h for h in driver.window_handles if h != reup_fb_tab_handle]
        if other_tabs: main.initial_main_tab = other_tabs[0]
        else: 
            driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
            main.initial_main_tab = driver.window_handles[-1]
        driver.switch_to.window(main.initial_main_tab)

    for index, list_line_item in enumerate(uspto_search_items):
        print(f"\n--- Xử lý mục {index + 1}/{len(uspto_search_items)}: '{list_line_item}' ---")
        if main.initial_main_tab not in driver.window_handles:
            print("CẢNH BÁO: Tab USPTO có thể đã bị đóng. Mở lại tab USPTO.")
            driver.execute_script("window.open('about:blank', '_blank');"); time.sleep(0.5)
            main.initial_main_tab = driver.window_handles[-1]
        driver.switch_to.window(main.initial_main_tab)

        parts = list_line_item.split(' - ', 1)
        search_term_uspto = parts[0].strip()
        website_for_trademark_form = parts[1].strip() if len(parts) > 1 else ""
        if not search_term_uspto: print("   USPTO: Bỏ qua dòng trống."); continue

        extracted_wordmark_from_uspto, extracted_serial, extracted_owners = "", "", ""
        try: 
            driver.get(URL_USPTO_SEARCH)
            wait_uspto = WebDriverWait(driver, 20)
            print(f"   USPTO: Tìm kiếm '{search_term_uspto.lower()}'...")
            search_box = wait_uspto.until(EC.presence_of_element_located((By.ID, "searchbar")))
            search_box.clear(); search_box.send_keys(search_term_uspto.lower()); search_box.send_keys(Keys.ENTER)
            try:
                wait_uspto.until(EC.any_of(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'listTitle') and text()='Wordmark']")),
                    EC.visibility_of_element_located((By.ID, "searchResultsContainer")), 
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(text(),'No results found')]"))
                ));
            except: print(f"   USPTO: Lỗi chờ kết quả.")

            try: 
                status_checkbox = wait_uspto.until(EC.element_to_be_clickable((By.ID, "statusDead")))
                if not status_checkbox.is_selected():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", status_checkbox); time.sleep(0.5)
                    clicked_sd = False
                    try: status_checkbox.click(); clicked_sd = True;
                    except:
                        try: driver.execute_script("arguments[0].click();", status_checkbox); clicked_sd = True;
                        except Exception as e_js_sd: print(f"   USPTO: JS click 'statusDead' cũng lỗi: {e_js_sd}.")
                    if clicked_sd:
                        time.sleep(0.5); current_sd_state = driver.find_element(By.ID, "statusDead").is_selected()
                        if current_sd_state:
                            try: 
                                old_search_box_ref = driver.find_element(By.ID,"searchbar") 
                                WebDriverWait(driver,15).until(EC.staleness_of(old_search_box_ref));
                            except: time.sleep(2) 
                            WebDriverWait(driver,15).until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'listTitle') and text()='Wordmark']/following-sibling::div//span[contains(@class, 'clickable')]")))
                time.sleep(0.5)
            except Exception as e_sd_block: print(f"   USPTO: Lỗi khối statusDead: {e_sd_block}")
            
            try:
                wordmark_full_text = wait_uspto.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'listTitle') and text()='Wordmark']/following-sibling::div//span[contains(@class, 'clickable')]"))).text
                extracted_wordmark_from_uspto = remove_duplicates_in_wordmark(wordmark_full_text.strip())
            except: extracted_wordmark_from_uspto = search_term_uspto
            try: extracted_serial = wait_uspto.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'listTitle') and text()='Serial']/following-sibling::div/span"))).text.strip()
            except: pass
            try:
                owners_raw_text = wait_uspto.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'listTitle') and text()='Owners']/following-sibling::div/span"))).text.strip()
                extracted_owners = re.sub(r'\(.*?\)', '', owners_raw_text).strip()
            except: pass
            print(f"   --- USPTO Info: W='{extracted_wordmark_from_uspto}', S='{extracted_serial}', O='{extracted_owners}' ---")

            # SỬA TÊN BIẾN Ở ĐÂY
            wordmark_for_post_and_Google_Search = search_term_uspto
            wordmark_for_facebook_form = extracted_wordmark_from_uspto if extracted_wordmark_from_uspto else search_term_uspto

            print("\n   Bắt đầu quy trình Reup Facebook...")
            reup_post_link = create_facebook_post_on_reup_tab(driver, 
                                                              WebDriverWait(driver, 20), WebDriverWait(driver, 75),
                                                              reup_profile_slug,
                                                              wordmark_for_post_and_Google_Search) # SỬA TÊN BIẾN Ở ĐÂY
            if not reup_post_link: print("   CẢNH BÁO: Không lấy được link bài reup.")
            
            if extracted_owners or wordmark_for_facebook_form:
                current_email_info = email_data_list[current_email_data_idx]
                form_result_ok = fill_trademark_form_and_verify_email(
                    driver, WebDriverWait(driver, 25), WebDriverWait(driver, 75), 
                    extracted_owners, current_email_info, 
                    website_for_trademark_form, 
                    wordmark_for_facebook_form,
                    extracted_serial, reup_post_link, additional_info_lines )
                if form_result_ok:
                    current_email_info['use_count'] += 1
                    print(f"   Email '{current_email_info['email']}' đã sử dụng thành công {current_email_info['use_count']} lần.")
                    if current_email_info['use_count'] >= 3:
                        print(f"   Chuyển sang email tiếp theo sau khi '{current_email_info['email']}' đã dùng 3 lần.")
                        current_email_info['use_count'] = 0
                        current_email_info['last_code'] = None 
                        current_email_data_idx = (current_email_data_idx + 1) % len(email_data_list)
                else: print("   CẢNH BÁO: Quy trình gửi form trademark và xác minh email KHÔNG thành công.")
            else: print("   USPTO: Không đủ thông tin để điền form Facebook Trademark.")
        except Exception as e_uspto_main:
            print(f"   Lỗi chính khi xử lý mục USPTO '{search_term_uspto}': {type(e_uspto_main).__name__} - {e_uspto_main}")
            try: driver.save_screenshot(f"uspto_loop_error_{time.strftime('%Y%m%d-%H%M%S')}.png")
            except: pass
        print(f"--- Kết thúc xử lý mục '{list_line_item}' ---"); time.sleep(random.uniform(3,5))

    print("\n\n======== HOÀN TẤT XỬ LÝ ========")
    input("Nhấn Enter để đóng trình duyệt...") 
    if driver: driver.quit(); print("Đã đóng trình duyệt.")

if __name__ == "__main__":
    main.initial_main_tab = None 
    main()