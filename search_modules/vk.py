# search_modules/vk.py

import requests  # Для выполнения HTTP-запросов к API VK
import time  # Для добавления задержек между запросами
import random  # Для случайных задержек, чтобы не превышать лимиты API
from datetime import datetime  # Для работы с датами и временем
from config import VK_ACCESS_TOKEN  # Токен доступа для работы с VK API
from search_engine import register_platform  # Декоратор для регистрации платформы

# Импортируем логгер из log_config.py для ведения логов
from log_config import logger

def get_city_id(city_name, access_token, api_version):
    """
    Получает ID города по его названию через API VK.
    Используется для фильтрации поиска по городу.
    Параметры:
        city_name (str): Название города.
        access_token (str): Токен доступа к VK API.
        api_version (str): Версия API VK.
    Возвращает:
        int или None: ID города, если найден, иначе None.
    """
    # Проверяем, передан ли город
    if not city_name:
        logger.warning("Запрос на получение ID города пустой. Пропускаю...")
        return None

    # Формируем URL и параметры для запроса
    url = "https://api.vk.com/method/database.getCities"
    params = {
        "country_id": 1,  # ID страны (1 = Россия)
        "q": city_name,  # Название города для поиска
        "access_token": access_token,  # Токен для авторизации
        "v": api_version  # Версия API
    }
    logger.info(f"Запрашиваю ID города {city_name} через VK API...")

    try:
        # Выполняем запрос к API
        response = requests.get(url, params=params)
        response.raise_for_status()  # Проверяем, есть ли ошибки HTTP
        data = response.json()
        logger.info(f"Получен ответ от VK для города {city_name}: {data}")

        # Проверяем структуру ответа и извлекаем ID города
        if "response" in data and "items" in data["response"] and data["response"]["items"]:
            city_id = data["response"]["items"][0]["id"]
            logger.info(f"Найден ID города {city_name}: {city_id}")
            return city_id
        logger.warning(f"Не удалось найти ID для города {city_name}.")
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении ID города {city_name}: {str(e)}. Пропускаю...")
        return None

# Регистрируем платформу VK с декоратором
# По умолчанию активна (active_by_default=True)
@register_platform("VK")
def vk_search(name=None, city=None, phone=None):
    """
    Выполняет поиск пользователя во ВКонтакте по имени, городу или телефону.
    Поддерживает поиск по имени (с @ или без) и фильтрацию по городу.
    Параметры:
        name (str): Имя или username пользователя (с @ или без).
        city (str): Название города для фильтрации.
        phone (str): Телефон (не поддерживается VK).
    Возвращает:
        tuple: (список результатов, ошибка или None).
    """
    results = []  # Список для хранения результатов поиска
    access_token = VK_ACCESS_TOKEN  # Токен доступа из конфига
    api_version = "5.199"  # Используем актуальную версию API VK

    # VK не поддерживает поиск по телефону, возвращаем ошибку
    if phone:
        logger.warning("VK не поддерживает поиск по телефону. Пропускаю...")
        return results, "VK does not support phone search."

    raw_results = []  # Сырые данные от API перед обработкой
    logger.info(f"Начинаю поиск во VK с параметрами: имя={name}, город={city}, телефон={phone}")

    # Проверяем тип поиска: по username или по имени
    if name and name.startswith("@"):
        # Поиск по username (начинается с @)
        username = name.lstrip("@")
        url = "https://api.vk.com/method/users.get"
        params = {
            "user_ids": username,  # Имя пользователя без @
            "fields": "photo_50,photo_100,photo_200,photo_400,photo_max_orig,domain,sex,bdate,status,last_seen,can_write_private_message,can_send_friend_request,screen_name,city",
            "access_token": access_token,
            "v": api_version
        }
        logger.info(f"Выполняю поиск по username {username} через users.get...")
        try:
            # Добавляем случайную задержку (1-3 секунды)
            time.sleep(random.uniform(1, 3))
            response = requests.get(url, params=params)
            response.raise_for_status()  # Проверяем HTTP-статус
            data = response.json()
            logger.info(f"Ответ от VK users.get для {username}: {data}")
            if "response" in data and data["response"]:
                raw_results = data["response"]
                logger.info(f"Найдено {len(raw_results)} записей для {username}.")
        except Exception as e:
            logger.error(f"Ошибка при поиске по username {username}: {str(e)}")
            return results, f"VK users.get error: {str(e)}"
    elif name and not name.startswith("@"):
        # Поиск по имени (без @) с фильтром по городу
        url = "https://api.vk.com/method/users.search"
        params = {
            "q": name,  # Поисковое имя
            "fields": "photo_50,photo_100,photo_200,photo_400,photo_max_orig,domain,sex,bdate,status,last_seen,can_write_private_message,can_send_friend_request,screen_name,city",
            "access_token": access_token,
            "v": api_version,
            "count": 50  # Ограничиваем до 50 результатов
        }
        # Добавляем фильтр по городу, если он указан
        if city:
            city_id = get_city_id(city, access_token, api_version)
            if city_id:
                params["city"] = city_id
                logger.info(f"Добавил фильтр по городу {city} с ID {city_id}.")
        logger.info(f"Выполняю поиск по имени {name} через users.search...")
        try:
            # Добавляем случайную задержку
            time.sleep(random.uniform(1, 3))
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Ответ от VK users.search для {name}: {data}")
            if "response" in data and "items" in data["response"]:
                raw_results = data["response"]["items"]
                logger.info(f"Найдено {len(raw_results)} пользователей по запросу {name}.")
        except Exception as e:
            logger.error(f"Ошибка при поиске по имени {name}: {str(e)}")
            return results, f"VK users.search error: {str(e)}"

    # Обрабатываем сырые данные и формируем результаты
    for user in raw_results:
        logger.info(f"Обрабатываю данные пользователя с ID {user.get('id')}...")
        # Получаем время последнего визита и форматируем его
        last_seen = user.get("last_seen", {}).get("time")
        last_seen_formatted = None
        if last_seen:
            last_seen_time = datetime.fromtimestamp(last_seen).strftime("%H:%M, %d %b %Y")
            # Маппинг платформ для читаемого формата
            platform_map = {1: "мобильное устройство", 4: "iPhone", 7: "браузер"}
            platform = platform_map.get(user.get("last_seen", {}).get("platform"), "неизвестное устройство")
            last_seen_formatted = f"{last_seen_time} ({platform})"
            logger.info(f"Отформатировал last_seen для пользователя: {last_seen_formatted}")

        # Формируем результат для каждого пользователя
        result = {
            "platform": "VK",  # Название платформы
            "timestamp": datetime.now().strftime("%m.%Y"),  # Месяц и год поиска
            "id": user.get("id"),  # Уникальный ID пользователя
            "domain": user.get("domain"),  # Домен профиля
            "full_name": f"{user.get('first_name', 'No name')} {user.get('last_name', '')}".strip(),  # Полное имя
            "screen_name": user.get("screen_name"),  # Псевдоним
            "sex": "мужской" if user.get("sex") == 2 else "женский" if user.get("sex") == 1 else "не указан",  # Пол
            "bdate": user.get("bdate"),  # Дата рождения
            "status": user.get("status"),  # Статус
            "city": user.get("city", {}).get("title") if user.get("city") else "Неизвестно",  # Город
            "last_seen": last_seen_formatted,  # Форматированное время последнего визита
            "can_write_private_message": bool(user.get("can_write_private_message")),  # Можно ли писать
            "can_send_friend_request": bool(user.get("can_send_friend_request")),  # Можно ли отправить запрос
            "has_photo": bool(user.get("has_photo")),  # Есть ли фото
            "photo": user.get("photo_200"),  # URL фото 200x200
            "photo_50": user.get("photo_50"),  # URL фото 50x50
            "photo_100": user.get("photo_100"),  # URL фото 100x100
            "photo_400": user.get("photo_400"),  # URL фото 400x400
            "photo_max_orig": user.get("photo_max_orig"),  # URL максимального фото
            "is_closed": user.get("is_closed", False),  # Закрыт ли профиль
            "exif_data": {},  # Поле для EXIF (пока пустое)
            "phones": [phone] if phone else []  # Телефон, если указан
        }
        results.append(result)
        logger.info(f"Добавлен результат для пользователя ID {user.get('id')}.")

    logger.info(f"Поиск во VK завершён. Найдено {len(results)} пользователей.")
    return results, None  # Возвращаем результаты и None, если ошибок нет