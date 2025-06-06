# search_modules/telegram.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from log_config import logger
from config import TELEGRAM_BOT_TOKEN
from search_engine import register_platform
import time
from urllib.parse import urlparse

def fetch_telegram_page(url, headers, proxy=None, max_retries=3):
    """
    Выполняет запрос к странице Telegram и возвращает HTML-ответ.
    
    Args:
        url (str): URL страницы Telegram (например, https://t.me/username)
        headers (dict): Заголовки HTTP-запроса для имитации браузера
        proxy (dict, optional): Прокси для запроса
        max_retries (int): Максимальное количество попыток при ошибке
        
    Returns:
        Response: Объект ответа от requests
        
    Raises:
        requests.RequestException: При ошибке сети или сервера
    """
    logger.info(f"Отправляю запрос к странице Telegram: {url}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url, 
                headers=headers, 
                proxies=proxy,
                allow_redirects=True, 
                timeout=10
            )
            response.raise_for_status()
            logger.debug(f"Успешно получил ответ с кодом: {response.status_code}")
            return response
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Попытка {attempt + 1} не удалась: {str(e)}. Ожидание {wait_time} секунд...")
                time.sleep(wait_time)
            else:
                logger.error(f"Все попытки запроса к {url} не удались: {str(e)}")
                raise

def parse_telegram_profile(soup, username, url, phone=None):
    """
    Парсит HTML-страницу профиля Telegram и извлекает информацию о пользователе.
    
    Args:
        soup (BeautifulSoup): Объект BeautifulSoup с HTML-страницей
        username (str): Имя пользователя без @
        url (str): URL профиля
        phone (str, optional): Телефон пользователя
        
    Returns:
        dict: Словарь с информацией о пользователе, содержащий следующие поля:
            - platform: Название платформы
            - timestamp: Время поиска
            - username: Имя пользователя
            - profile_link: Ссылка на профиль
            - full_name: Полное имя
            - description: Описание профиля
            - photo: URL фото профиля
            - extra_info: Дополнительная информация
            - phone: Телефон
            - subscribers: Количество подписчиков
            - is_verified: Статус верификации
            - work: Место работы
            - position: Должность
    """
    # Получаем основные элементы страницы
    title_elem = soup.find("span", class_="tgme_page_title")
    description_elem = soup.find("div", class_="tgme_page_description")
    photo_elem = soup.find("img", class_="tgme_page_photo_image")
    extra_info_elem = soup.find("div", class_="tgme_page_extra")
    
    # Получаем дополнительную информацию
    subscribers_elem = soup.find("div", class_="tgme_page_counter")
    verification_elem = soup.find("i", class_="verified-icon")
    
    # Извлекаем количество подписчиков
    subscribers = "0"
    if subscribers_elem:
        subscribers_text = subscribers_elem.text.strip()
        if "subscribers" in subscribers_text.lower():
            subscribers = subscribers_text.split()[0]
    elif extra_info_elem:
        extra_text = extra_info_elem.text.strip()
        if "subscribers" in extra_text.lower():
            subscribers = extra_text.split("subscribers")[0].strip()
    
    # Проверяем верификацию
    is_verified = bool(verification_elem)
    
    # Получаем полное имя
    full_name = title_elem.text.strip() if title_elem else "Неизвестно"
    
    # Формируем результат
    result = {
        "platform": "Telegram",
        "timestamp": datetime.now().strftime("%m.%Y"),
        "username": username,
        "profile_link": url,
        "full_name": full_name,
        "description": description_elem.text.strip() if description_elem else "Нет описания",
        "photo": photo_elem["src"] if photo_elem and "src" in photo_elem.attrs else None,
        "extra_info": extra_info_elem.text.strip() if extra_info_elem else "Нет дополнительной информации",
        "phone": phone if phone else "Неизвестно",
        "subscribers": subscribers,
        "is_verified": is_verified,
        "work": description_elem.text.strip() if description_elem and "Founder" in description_elem.text else "Не указано",
        "position": "Founder" if description_elem and "Founder" in description_elem.text else "Не указано"
    }
    
    # Форматируем текстовые поля
    if result["description"] != "Нет описания":
        result["description"] = result["description"].replace("\n", ", ")
    
    if result["extra_info"] != "Нет дополнительной информации":
        result["extra_info"] = result["extra_info"].replace("\n", ", ")
    
    return result

@register_platform("Telegram")
def telegram_search(name=None, city=None, phone=None, proxy=None):
    """
    Выполняет поиск пользователя в Telegram по имени пользователя.
    
    Args:
        name (str): Имя пользователя (должно начинаться с @)
        city (str): Город (не используется)
        phone (str): Телефон (опционально)
        proxy (dict): Прокси для запроса (опционально)
        
    Returns:
        tuple: (список результатов, ошибка или None)
    """
    logger.info(f"Запускаю поиск в Telegram с параметрами: имя={name}, город={city}, телефон={phone}")
    results = []

    # Заголовки для имитации браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }

    if name and name.startswith("@"):
        username = name.lstrip("@")
        url = f"https://t.me/{username}"
        logger.debug(f"Пытаюсь получить данные с {url}")

        try:
            response = fetch_telegram_page(url, headers, proxy)

            if "This user does not exist" in response.text or "tgme_page_title" not in response.text:
                logger.debug(f"Пользователь {name} не найден в Telegram.")
                return results, f"Пользователь {name} не найден в Telegram."

            soup = BeautifulSoup(response.text, "html.parser")
            result = parse_telegram_profile(soup, username, url, phone)
            results.append(result)
            logger.debug(f"Найден пользователь в Telegram: {result}")

        except requests.RequestException as e:
            logger.error(f"Сбой при запросе к {url}: {str(e)}")
            return results, f"Ошибка сети Telegram для {name}: {str(e)}"
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке {url}: {str(e)}")
            return results, f"Неожиданная ошибка Telegram для {name}: {str(e)}"
    else:
        logger.warning(f"Некорректный запрос в Telegram: имя {name} не начинается с '@' или не указано.")
        return results, "Некорректный формат имени пользователя Telegram (должно начинаться с @)"

    logger.info(f"Поиск в Telegram завершён. Результаты: {results}")
    return results, None if results else "Результаты не найдены для платформы Telegram."