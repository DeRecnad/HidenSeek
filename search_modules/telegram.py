# search_modules/telegram.py

import requests  # Для выполнения HTTP-запросов к Telegram
from bs4 import BeautifulSoup  # Для парсинга HTML-страниц Telegram
from datetime import datetime  # Для работы с датами и временем
from log_config import logger  # Импортируем настроенный логгер из log_config.py
from config import TELEGRAM_BOT_TOKEN  # Токен бота Telegram (хотя здесь не используется напрямую)
from search_engine import register_platform  # Декоратор для регистрации платформы

def fetch_telegram_page(url, headers):
    """
    Выполняет запрос к указанной странице Telegram и возвращает HTML-ответ.
    Параметры:
        url (str): URL страницы Telegram (например, https://t.me/username).
        headers (dict): Заголовки HTTP-запроса для имитации браузера.
    Возвращает:
        Response: Объект ответа от requests или вызывает исключение при ошибке.
    """
    logger.info(f"Отправляю запрос к странице Telegram: {url}")
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()  # Проверяем, есть ли ошибки HTTP (например, 404 или 500)
        logger.debug(f"Успешно получил ответ с кодом: {response.status_code}")
        logger.debug(f"Текст ответа (первые 500 символов): {response.text[:500]}...")
        return response
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к {url}: {str(e)}. Проблемы с сетью!")
        raise  # Передаём исключение выше для обработки

# Регистрируем платформу Telegram с декоратором
# По умолчанию активна (active_by_default=True не указан, значит True)
@register_platform("Telegram")
def telegram_search(name=None, city=None, phone=None):
    """
    Выполняет поиск пользователя в Telegram по имени (username, начинающемуся с @).
    Парсит публичную страницу пользователя для получения информации.
    Параметры:
        name (str): Имя пользователя (должно начинаться с @).
        city (str): Город (не используется в данном случае).
        phone (str): Телефон (может быть включён в результат, если указан).
    Возвращает:
        tuple: (список результатов, ошибка или None).
    """
    logger.info(f"Запускаю поиск в Telegram с параметрами: имя={name}, город={city}, телефон={phone}")
    results = []  # Список для хранения результатов поиска

    # Устанавливаем заголовки для имитации браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Проверяем, передан ли параметр name и начинается ли он с @
    if name and name.startswith("@"):
        username = name.lstrip("@")  # Удаляем @ для формирования URL
        url = f"https://t.me/{username}"  # Формируем URL публичной страницы
        logger.debug(f"Пытаюсь получить данные с {url} с заголовками: {headers}")

        try:
            # Выполняем запрос к странице Telegram
            response = fetch_telegram_page(url, headers)

            # Проверяем, существует ли пользователь
            if "This user does not exist" in response.text or "tgme_page_title" not in response.text:
                logger.debug(f"Пользователь {name} не найден в Telegram.")
            else:
                # Парсим HTML-страницу с помощью BeautifulSoup
                logger.info(f"Парсинг страницы {url} для пользователя {username}...")
                soup = BeautifulSoup(response.text, "html.parser")

                # Извлекаем элементы страницы
                title_elem = soup.find("span", class_="tgme_page_title")  # Имя пользователя
                description_elem = soup.find("div", class_="tgme_page_description")  # Описание
                photo_elem = soup.find("img", class_="tgme_page_photo_image")  # Фото профиля
                extra_info_elem = soup.find("div", class_="tgme_page_extra")  # Дополнительная информация

                # Формируем данные о пользователе
                full_name = title_elem.text.strip() if title_elem else "Неизвестно"
                result = {
                    "platform": "Telegram",  # Название платформы
                    "timestamp": datetime.now().strftime("%m.%Y"),  # Месяц и год поиска
                    "username": username,  # Имя пользователя без @
                    "profile_link": url,  # Ссылка на профиль
                    "full_name": full_name,  # Полное имя или "Неизвестно"
                    "description": description_elem.text.strip() if description_elem else "Нет описания",  # Описание
                    "photo": photo_elem["src"] if photo_elem and "src" in photo_elem.attrs else None,  # URL фото
                    "extra_info": extra_info_elem.text.strip() if extra_info_elem else "Нет дополнительной информации",  # Доп. данные
                    "phone": phone if phone else "Неизвестно",  # Телефон, если указан
                    "can_write_private_message": False,  # Telegram не предоставляет эту информацию публично
                    "can_send_friend_request": False,  # Аналогично
                    "is_closed": False,  # Предполагаем, что публичный профиль
                    "exif_data": {},  # Поле для EXIF (пока не используется)
                    "phones": [phone] if phone else []  # Список телефонов
                }
                results.append(result)  # Добавляем результат в список
                logger.debug(f"Найден пользователь в Telegram: {result}")

        except requests.RequestException as e:
            # Обработка ошибок сети (например, таймаут или недоступность сервера)
            logger.error(f"Сбой при запросе к {url}: {str(e)}. Возвращаю пустой результат.")
            return results, f"Telegram network error for {name}: {str(e)}"
        except Exception as e:
            # Обработка неожиданных ошибок (например, проблемы с парсингом)
            logger.error(f"Неожиданная ошибка при обработке {url}: {str(e)}. Прерываю.")
            return results, f"Telegram unexpected error for {name}: {str(e)}"
    else:
        logger.warning(f"Некорректный запрос в Telegram: имя {name} не начинается с '@' или не указано.")
        # Если имя не указано или не начинается с @, возвращаем пустой результат

    logger.info(f"Поиск в Telegram завершён. Результаты: {results}")
    # Возвращаем результаты и None, если всё прошло успешно, или ошибку, если результатов нет
    return results, None if results else "No results found for platform Telegram."