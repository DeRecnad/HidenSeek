# search_modules/instagram.py

import os  # Для работы с файловой системой (проверка существования файла сессии)
import time  # Для задержек между запросами к Instagram
import random  # Для случайных задержек, чтобы не превышать лимиты API
from datetime import datetime  # Для создания временных меток
from instagrapi import Client  # Клиент для взаимодействия с Instagram API
from instagrapi.exceptions import ChallengeRequired, LoginRequired  # Обработка ошибок авторизации
from config import INSTAGRAM_EMAIL, INSTAGRAM_PASSWORD  # Данные для входа в Instagram
from search_engine import register_platform  # Декоратор для регистрации платформы

# Импортируем логгер из log_config.py для ведения логов
from log_config import logger

# Глобальная переменная для хранения клиента Instagram
# Инициализируется позже, чтобы избежать повторного создания
instagram_client = None

def initialize_instagram_client():
    """
    Инициализирует клиента Instagram, загружая существующую сессию или создавая новую.
    Если сессия недоступна или требуется повторная авторизация, пытается восстановить.
    """
    global instagram_client
    session_file = "instagram_session.json"  # Файл для сохранения сессии

    if instagram_client is None:
        try:
            # Создаём новый клиент Instagram
            logger.info(f"Создаю нового клиента для Instagram. Давай попробуем!")
            instagram_client = Client()
            # Устанавливаем случайные задержки между запросами (1-3 секунды)
            instagram_client.delay_range = [1, 3]

            if os.path.exists(session_file):
                # Если файл сессии существует, загружаем его
                logger.info(f"Нашёл файл сессии {session_file}. Загружаю его...")
                instagram_client.load_settings(session_file)
                logger.info("Вхожу в Instagram с сохранённой сессией...")
                instagram_client.login(INSTAGRAM_EMAIL, INSTAGRAM_PASSWORD)
                logger.info("Сессия Instagram успешно загружена! Всё готово!")
            else:
                # Если файла сессии нет, выполняем новый вход
                logger.info("Файл сессии не найден. Выполняю новый вход в Instagram...")
                instagram_client.login(INSTAGRAM_EMAIL, INSTAGRAM_PASSWORD)
                logger.info("Вход выполнен. Сохраняю сессию в файл...")
                instagram_client.dump_settings(session_file)
                logger.info(f"Сессия сохранена в {session_file}. Клиент готов к работе!")

        except ChallengeRequired:
            # Если требуется 2FA или разрешение челленджа
            logger.warning("Instagram запросил 2FA или разрешение челленджа. Нужно вмешательство!")
            instagram_client = None
        except LoginRequired:
            # Если сессия устарела, очищаем и повторяем попытку
            logger.warning("Сессия устарела. Очищаю и пытаюсь снова...")
            if os.path.exists(session_file):
                logger.info(f"Удаляю старый файл сессии {session_file}...")
                os.remove(session_file)
            initialize_instagram_client()  # Рекурсивный вызов для повторной инициализации
        except Exception as e:
            # Обработка других ошибок (например, проблемы с сетью)
            logger.error(f"Ошибка при инициализации клиента Instagram: {str(e)}. Что-то пошло не так!")
            instagram_client = None

# Регистрируем платформу Instagram с декоратором
# Указываем, что по умолчанию она неактивна (active_by_default=False)
@register_platform("Instagram", active_by_default=False)
def instagram_search(name=None, city=None, phone=None):
    """
    Выполняет поиск пользователя в Instagram по имени (username).
    Возвращает список результатов с информацией о пользователе и его медиа (если аккаунт публичный).
    Параметры:
        name (str): Имя пользователя (должно начинаться с @).
        city (str): Город (не используется в данном случае).
        phone (str): Телефон (не используется в данном случае).
    Возвращает:
        tuple: (список результатов, ошибка или None).
    """
    results = []  # Список для хранения результатов поиска
    # Проверяем, передан ли параметр name и начинается ли он с @
    if not name or not name.startswith("@"):
        logger.warning("Запрос в Instagram невалиден: имя должно начинаться с '@'.")
        return results, "Instagram search: Username must start with '@'"

    # Удаляем @ из начала имени для использования в API
    username = name.lstrip("@")
    logger.info(f"Начинаю поиск пользователя {username} в Instagram...")

    try:
        # Инициализируем клиента, если он ещё не создан
        if instagram_client is None:
            logger.info("Клиент Instagram ещё не инициализирован. Запускаю процесс...")
            initialize_instagram_client()
        if not instagram_client:
            # Если клиент не инициализирован (например, из-за ошибки), прерываем
            logger.error("Не удалось инициализировать клиент Instagram. Прерываю поиск!")
            raise Exception("Instagram client failed to initialize")

        # Получаем ID пользователя по имени
        logger.info(f"Получаю ID пользователя {username}...")
        user_id = instagram_client.user_id_from_username(username)
        logger.info(f"Найден ID пользователя: {user_id}")

        # Получаем полную информацию о пользователе
        logger.info(f"Собираю данные о пользователе {username}...")
        user_info = instagram_client.user_info(user_id).dict()
        logger.info(f"Получена информация о пользователе: {user_info}")

        # Формируем результат поиска
        result = {
            "platform": "Instagram",  # Название платформы
            "timestamp": datetime.now().strftime("%m.%Y"),  # Месяц и год поиска
            "username": username,  # Имя пользователя
            "profile_link": f"https://www.instagram.com/{username}/",  # Ссылка на профиль
            "full_name": user_info.get("full_name", "N/A"),  # Полное имя или N/A
            "biography": user_info.get("biography", "N/A"),  # Биография или N/A
            "follower_count": user_info.get("follower_count", 0),  # Количество подписчиков
            "following_count": user_info.get("following_count", 0),  # Количество подписок
            "is_private": user_info.get("is_private", True),  # Приватный ли аккаунт
            "external_url": user_info.get("external_url", "N/A"),  # Внешняя ссылка
            "is_verified": user_info.get("is_verified", False),  # Подтверждён ли аккаунт
            "photo": str(user_info.get("profile_pic_url", "N/A")),  # URL аватарки
            "phones": []  # Пока телефоны не поддерживаются
        }

        # Если аккаунт публичный, загружаем последние 3 фото
        if not user_info.get("is_private", True):
            logger.info(f"Аккаунт {username} публичный. Загружаю последние 3 фото...")
            media = instagram_client.user_medias(user_id, amount=3)  # Получаем до 3 медиа
            photo_count = 0  # Счётчик найденных фото
            for m in media:
                if m.media_type == 1 and photo_count < 3:  # 1 = фото
                    photo_count += 1
                    # Добавляем URL миниатюры фото
                    result[f"Photo_{photo_count}"] = str(m.thumbnail_url) if m.thumbnail_url else "N/A"
                    logger.info(f"Найдено фото {photo_count}: {result[f'Photo_{photo_count}']}")
                # Добавляем случайную задержку, чтобы не превысить лимиты API
                time.sleep(random.uniform(1, 3))

        # Добавляем результат в список
        results.append(result)
        logger.info(f"Поиск для {username} завершён. Найдено {len(results)} записей.")

    except Exception as e:
        # Обработка ошибок (например, пользователь не найден)
        logger.error(f"Ошибка при поиске {username} в Instagram: {str(e)}")
        result = {
            "platform": "Instagram",
            "timestamp": datetime.now().strftime("%m.%Y"),
            "username": username,
            "error": str(e),
            "full_name": "N/A",
            "photo": None,
            "phones": []
        }
        results.append(result)
        logger.info(f"Добавил запись об ошибке для {username} в результаты.")

    # Возвращаем результаты и None, если ошибок нет
    return results, None