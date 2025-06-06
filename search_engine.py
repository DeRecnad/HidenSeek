# search_engine.py

from collections import defaultdict  # Для подсчёта частоты данных (например, имён)
from datetime import datetime  # Для работы с датами и временем
import time  # Для добавления задержек между запросами
import random  # Для случайных задержек, чтобы не превышать лимиты

# Импортируем настроенный логгер из log_config.py для ведения логов
from log_config import logger

# Импортируем токен Telegram (хотя здесь он не используется напрямую)
from config import TELEGRAM_BOT_TOKEN

# Глобальный реестр платформ, где хранятся зарегистрированные платформы
# Ключи — нижний регистр названий платформ, значения — их данные
PLATFORM_REGISTRY = {}

def register_platform(name, active_by_default=True):
    """
    Декоратор для регистрации новой платформы в глобальном реестре PLATFORM_REGISTRY.
    Позволяет связать функцию поиска с платформой и установить её состояние по умолчанию.
    Параметры:
        name (str): Название платформы (например, "VK", "Instagram").
        active_by_default (bool): Активна ли платформа по умолчанию (True по умолчанию).
    Возвращает:
        function: Декорированную функцию поиска.
    """
    def decorator(func):
        # Преобразуем название платформы в нижний регистр для унификации
        key = name.lower()
        if key not in PLATFORM_REGISTRY:
            # Регистрируем новую платформу с её именем, функцией поиска и состоянием
            PLATFORM_REGISTRY[key] = {
                "name": name,
                "search_func": func,
                "active_by_default": active_by_default
            }
            logger.info(f"Зарегистрировал новую платформу: {key} -> {name}. Всё готово!")
        else:
            # Если платформа уже зарегистрирована, просто пропускаем
            logger.info(f"Платформа {key} уже зарегистрирована, пропускаю дубликат.")
        return func  # Возвращаем оригинальную функцию без изменений
    return decorator

# Логируем начальное состояние реестра платформ
logger.info(f"Изначально зарегистрированные платформы: {list(PLATFORM_REGISTRY.keys())}")

def create_person_passport(results):
    """Создает компактный паспорт человека из данных всех платформ"""
    passport = {
        'type': 'person_passport',
        'data': {
            'basic_info': {
                'full_name': None,
                'birth_date': None,
                'gender': None,
                'age': None,
                'location': None,
                'education': None,
                'work': None,
                'position': None
            },
            'contact_info': {
                'phones': set(),
                'emails': set()
            },
            'devices': {
                'ip_addresses': set()
            },
            'platforms': {
                'vk': False,
                'telegram': False,
                'instagram': False,
                'facebook': False
            }
        }
    }

    # Обрабатываем результаты от каждой платформы
    for result in results:
        if not result:
            continue

        # Отмечаем наличие платформы
        if 'platform' in result:
            platform = result['platform'].lower()
            if platform in passport['data']['platforms']:
                passport['data']['platforms'][platform] = True

        # Основная информация
        if result.get('full_name'):
            passport['data']['basic_info']['full_name'] = result['full_name']
        elif result.get('first_name') or result.get('last_name'):
            name_parts = [result.get('first_name', ''), result.get('last_name', '')]
            passport['data']['basic_info']['full_name'] = ' '.join(filter(None, name_parts))

        if result.get('bdate'):
            passport['data']['basic_info']['birth_date'] = result['bdate']
        if result.get('sex'):
            passport['data']['basic_info']['gender'] = result['sex']
        if result.get('age'):
            passport['data']['basic_info']['age'] = result['age']
        if result.get('city'):
            passport['data']['basic_info']['location'] = result['city']
        if result.get('education'):
            passport['data']['basic_info']['education'] = result['education']

        # Работа
        if result.get('career') and len(result['career']) > 0:
            latest_job = result['career'][0]
            if latest_job.get('company'):
                passport['data']['basic_info']['work'] = latest_job['company']
            if latest_job.get('position'):
                passport['data']['basic_info']['position'] = latest_job['position']

        # Контактная информация
        if result.get('phone'):
            passport['data']['contact_info']['phones'].add(result['phone'])
        if result.get('phones'):
            passport['data']['contact_info']['phones'].update(result['phones'])
        if result.get('email'):
            passport['data']['contact_info']['emails'].add(result['email'])
        if result.get('emails'):
            passport['data']['contact_info']['emails'].update(result['emails'])

        # IP адреса
        if result.get('ip'):
            passport['data']['devices']['ip_addresses'].add(result['ip'])
        if result.get('ip_addresses'):
            passport['data']['devices']['ip_addresses'].update(result['ip_addresses'])

    # Преобразуем множества в списки
    passport['data']['contact_info']['phones'] = list(passport['data']['contact_info']['phones'])
    passport['data']['contact_info']['emails'] = list(passport['data']['contact_info']['emails'])
    passport['data']['devices']['ip_addresses'] = list(passport['data']['devices']['ip_addresses'])

    # Заменяем None на "Неизвестно"
    for section in passport['data'].values():
        if isinstance(section, dict):
            for key, value in section.items():
                if value is None:
                    section[key] = "Неизвестно"

    return passport

def search(name=None, city=None, phone=None, api_params=None, platform=None, platform_configs=None):
    """
    Координирует поиск по указанным платформам и агрегирует результаты.
    Теперь также создает компактный паспорт человека из собранных данных.
    """
    # Проверяем, передан ли параметр platform_configs
    if platform_configs is None:
        logger.error("Параметр platform_configs не передан! Это критично, прерываю.")
        raise ValueError("platform_configs must be provided")

    results = []  # Список для хранения всех результатов
    errors = []  # Список для хранения ошибок, если они возникнут

    # Логируем входные параметры для отладки
    logger.info(f"Запуск поиска - Имя: {name}, Город: {city}, Телефон: {phone}, Платформа: {platform}")
    logger.debug(f"Текущие конфигурации платформ: {platform_configs}")
    logger.debug(f"Зарегистрированные платформы: {list(PLATFORM_REGISTRY.keys())}")

    # Проверяем, зарегистрирована ли указанная платформа
    if platform and platform.lower() not in PLATFORM_REGISTRY:
        logger.warning(f"Платформа {platform} не зарегистрирована. Возвращаю пустой результат.")
        return [], f"Platform {platform} is not registered."

    # Фильтруем платформы для поиска
    platforms = []  # Список кортежей (имя платформы, функция поиска)
    for key, entry in PLATFORM_REGISTRY.items():
        # Если указана конкретная платформа, проверяем только её
        if platform is None or key == platform.lower():
            is_active = platform_configs.get(key, {}).get("active", entry["active_by_default"])
            logger.debug(f"Платформа {key}: активна={is_active}, по умолчанию={entry['active_by_default']}")
            if is_active:
                platforms.append((entry["name"], entry["search_func"]))
                logger.debug(f"Добавил платформу {key} в список для поиска.")
            else:
                logger.debug(f"Пропускаю платформу {key}, так как она неактивна.")

    # Логируем список платформ, которые будут обработаны
    logger.info(f"Платформы для поиска: {[name for name, _ in platforms]}")

    # Словарь для хранения результатов по платформам
    platform_results_dict = {}
    for platform_name, search_func in platforms:
        logger.info(f"Начинаю просмотр платформы {platform_name}...")
        # Добавляем случайную задержку (0.5-1.5 секунды) между запросами
        time.sleep(random.uniform(0.5, 1.5))
        try:
            # Выполняем поиск для текущей платформы
            platform_results, error = search_func(name, city, phone)
            logger.debug(f"Функция поиска для {platform_name} вернула: результаты={platform_results}, ошибка={error}")
            platform_results_dict[platform_name] = platform_results if platform_results else []
            if error:
                errors.append(f"{platform_name}: {error}")
                logger.warning(f"Обнаружена ошибка для {platform_name}: {error}")
        except Exception as e:
            logger.error(f"Исключение при поиске на платформе {platform_name}: {str(e)}")
            errors.append(f"{platform_name}: {str(e)}")
            platform_results_dict[platform_name] = []

    # Если указана конкретная платформа, возвращаем только её результаты
    if platform:
        platform_key = PLATFORM_REGISTRY.get(platform.lower(), {}).get("name", platform)
        results = platform_results_dict.get(platform_key, [])
        logger.debug(f"Возвращаю результаты для {platform.upper()}: {results}")
        if not results:
            logger.warning(f"Не найдено результатов для платформы {platform}.")
            return results, f"No results found for platform {platform}."
        return results, "; ".join(errors) if errors else None

    # Создаем паспорт человека из собранных данных
    person_passport = create_person_passport(results)
    
    # Добавляем паспорт в результаты
    results.append(person_passport)

    # Агрегация данных (выполняется только если platform=None)
    logger.info("Начинаю агрегацию данных из всех платформ...")
    aggregated_data = {
        "full_name": defaultdict(int),  # Частота встречаемости имён
        "phones": defaultdict(int),  # Частота встречаемости телефонов
        "photo": None,  # Лучшее фото (берём первое непустое)
        "status": None,  # Статус (берём первый непустой)
        "last_seen": None,  # Последний визит (берём первый непустой)
        "bdate": None  # Дата рождения (берём первую непустую)
    }

    # Обход результатов по всем платформам
    for platform_name, platform_results in platform_results_dict.items():
        logger.debug(f"Агрегирую данные из платформы {platform_name}...")
        for result in platform_results:
            full_name = result.get("full_name", "Неизвестно")
            if full_name != "Неизвестно":
                aggregated_data["full_name"][full_name] += 1  # Увеличиваем счётчик для имени
            if "photo" in result and result["photo"] and not aggregated_data["photo"]:
                aggregated_data["photo"] = result["photo"]  # Берём первое фото
            if "status" in result and result["status"] and not aggregated_data["status"]:
                aggregated_data["status"] = result["status"]  # Берём первый статус
            if "last_seen" in result and result["last_seen"] and not aggregated_data["last_seen"]:
                aggregated_data["last_seen"] = result["last_seen"]  # Берём первый last_seen
            if "bdate" in result and result["bdate"] and not aggregated_data["bdate"]:
                aggregated_data["bdate"] = result["bdate"]  # Берём первую дату рождения
            for p in result.get("phones", []):
                aggregated_data["phones"][p] += 1  # Увеличиваем счётчик для телефона

    # Формируем финальный агрегированный результат
    final_result = {
        "platform": "Aggregated",  # Метка агрегированных данных
        "timestamp": datetime.now().strftime("%m.%Y"),  # Месяц и год
        "full_name": max(aggregated_data["full_name"], key=aggregated_data["full_name"].get) if aggregated_data["full_name"] else "Unknown",  # Самое частое имя
        "phones": list(aggregated_data["phones"].keys()),  # Список уникальных телефонов
        "photo": aggregated_data["photo"],  # Фото
        "status": aggregated_data["status"],  # Статус
        "last_seen": aggregated_data["last_seen"],  # Последний визит
        "bdate": aggregated_data["bdate"]  # Дата рождения
    }
    results.append(final_result)
    logger.debug(f"Агрегированный результат: {final_result}")

    # Добавляем результаты от всех платформ
    for platform_name, platform_results in platform_results_dict.items():
        logger.debug(f"Добавляю результаты от платформы {platform_name}: {platform_results}")
        results.extend(platform_results)

    # Проверяем, есть ли результаты
    if not results:
        logger.warning("Не найдено ни одной записи или информации по всем платформам.")
        return results, "No accounts or information found across all platforms."

    logger.info(f"Поиск завершён. Найдено {len(results)} записей. Ошибки: {errors}")
    return results, "; ".join(errors) if errors else None  # Возвращаем результаты и ошибки, если есть