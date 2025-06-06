# main.py

import os  # Для работы с файловой системой (проверка и создание папок)
import time  # Для работы со временем (например, генерация временных меток)
import random  # Для генерации случайных данных (если нужно)
from datetime import datetime  # Для работы с датой и временем
from yarl import URL  # Для работы с URL-адресами (преобразование в строку)
import importlib  # Для динамической загрузки модулей
import glob  # Для поиска файлов в директории (например, модулей в search_modules)
from config import SECRET_KEY # Импортируем секретный ключ из config.py для FLASK

# Импортируем настроенный логгер из log_config.py для ведения логов
from log_config import logger

# Импортируем Flask и его компоненты для создания веб-приложения
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename  # Для безопасной обработки имён файлов

# Импортируем функции и данные из других модулей проекта
from search_engine import search, PLATFORM_REGISTRY  # Функция поиска и список платформ
from platform_configs import toggle_platform, platform_configs  # Управление настройками платформ
from exif_processor import convert_heic_to_jpeg, extract_exif_with_exiftool  # Обработка изображений
from database import init_db, save_image, get_image_by_filename, get_image_history, debug_db  # Работа с базой данных

# Логируем начальную информацию о зарегистрированных платформах
# Это помогает понять, какие платформы доступны для поиска на старте
logger.info(f"Проверяю зарегистрированные платформы на старте: {list(PLATFORM_REGISTRY.keys())}")

# Динамически импортируем модули из папки search_modules
# Это нужно, чтобы автоматически подключить все модули поиска (например, VK, Telegram)
try:
    import search_modules
    logger.info("Успешно загрузил модуль search_modules. Всё готово для поиска!")
    # Ищем все .py файлы в папке search_modules
    module_files = glob.glob(os.path.join("search_modules", "*.py"))
    for module_file in module_files:
        # Получаем имя модуля без .py (например, "vk" из "vk.py")
        module_name = os.path.basename(module_file).replace(".py", "")
        # Пропускаем __init__.py, так как это не модуль платформы
        if module_name != "__init__":
            try:
                # Динамически импортируем модуль (например, search_modules.vk)
                importlib.import_module(f"search_modules.{module_name}")
                logger.info(f"Подключил модуль search_modules.{module_name}. Отлично, всё работает!")
            except Exception as e:
                # Если модуль не удалось подключить, логируем ошибку
                logger.error(f"Не смог подключить search_modules.{module_name}. Ошибка: {str(e)}")
except Exception as e:
    # Если произошла ошибка при загрузке всего пакета search_modules, тоже логируем
    logger.error(f"Проблема с загрузкой search_modules: {str(e)}. Нужно проверить!")

# Создаём приложение Flask
app = Flask(__name__)
# Устанавливаем секретный ключ для работы с сессиями
app.secret_key = SECRET_KEY
# Указываем папку для загрузки файлов
app.config["UPLOAD_FOLDER"] = "static/uploads"
# Ограничиваем максимальный размер загружаемого файла (16 МБ)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Импортируем модуль для обработки EXIF-данных из изображений
try:
    import exif_processor
    logger.info("Загрузил exif_processor. Теперь могу обрабатывать EXIF-данные!")
except ImportError:
    # Если модуль не найден, создаём заглушку, чтобы приложение не упало
    logger.warning("Модуль exif_processor не найден. Перехожу на заглушку, чтобы продолжить работу.")
    class DummyExifProcessor:
        # Заглушка для метода обработки изображения
        @staticmethod
        def process_image(file_path, exif_data=None):
            logger.info(f"Использую заглушку для обработки {file_path}. EXIF-данные пока недоступны.")
            return {}, "<p>No map available (exif_processor not implemented)</p>"
    exif_processor = DummyExifProcessor()

# Функция для преобразования данных в формат, пригодный для JSON
def serialize_result(result):
    """
    Рекурсивно преобразует объекты (например, URL) в строки для сериализации в JSON.
    Это нужно, чтобы данные можно было отправить клиенту через API.
    """
    if isinstance(result, dict):
        # Если это словарь, обрабатываем все его ключи и значения
        return {key: serialize_result(value) for key, value in result.items() if value is not None}
    elif isinstance(result, list):
        # Если это список, обрабатываем каждый элемент
        return [serialize_result(item) for item in result if item is not None]
    elif isinstance(result, URL):
        # Если это объект URL, преобразуем его в строку
        return str(result)
    elif isinstance(result, (int, float)):
        # Числа оставляем без изменений
        return result
    # Всё остальное преобразуем в строку
    return str(result)

# Функция для обработки поиска
def handle_search(name, city, phone, platform_type):
    logger.info(f"Начинаю поиск на платформе {platform_type}...")
    try:
        results, error = search(name=name, city=city, phone=phone, platform=platform_type, platform_configs=platform_configs)
        logger.info(f"Результаты поиска для {platform_type}: {results}. Ошибка: {error if error else 'нет'}")
        return results, error
    except Exception as e:
        logger.error(f"Произошла ошибка при поиске на {platform_type}: {str(e)}")
        return None, str(e)

# Функция для обработки загрузки изображений
def handle_image_upload(file):
    if file and file.filename:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)
        logger.info(f"Изображение {filename} успешно загружено.")
        return filename
    return None

# Главная страница приложения
@app.route("/", methods=["GET", "POST"])
def index():
    """
    Обрабатывает главную страницу (advanced_search.html).
    Если пользователь отправляет форму (POST), сохраняет параметры поиска и перенаправляет на страницу результатов.
    Если это GET-запрос, просто отображает форму.
    """
    logger.info("Открываю главную страницу (advanced_search.html).")
    if request.method == "POST":
        # Получаем данные из формы
        name = request.form.get("name", "").strip()
        city = request.form.get("city", "").strip()
        phone = request.form.get("phone", "").strip()
        logger.info(f"Получил данные для поиска: имя={name}, город={city}, телефон={phone}.")
        # Сохраняем параметры в сессии, чтобы использовать их позже
        session['search_params'] = {'name': name, 'city': city, 'phone': phone}
        logger.info("Сохранил параметры поиска в сессии. Перенаправляю на страницу результатов.")
        return redirect(url_for("search_results"))
    # Если это GET-запрос, просто отображаем форму
    return render_template("advanced_search.html")

# Страница результатов поиска
@app.route("/search_results", methods=["GET"])
def search_results():
    """
    Отображает страницу результатов поиска (search_results.html).
    Извлекает параметры поиска из сессии и передаёт их в шаблон.
    """
    # Получаем параметры поиска из сессии
    search_params = session.get('search_params', {})
    name = search_params.get('name')
    city = search_params.get('city')
    phone = search_params.get('phone')
    # Формируем строку запроса для отображения
    query = f"Name: {name or ''}, City: {city or ''}, Phone: {phone or ''}".strip()
    logger.info(f"Открываю страницу результатов поиска. Запрос: {query}")
    # Отображаем шаблон с параметрами
    return render_template("search_results.html", query=query)

# API-метод для получения списка доступных платформ
@app.route("/get_platforms", methods=["GET"])
def get_platforms():
    """
    Возвращает список платформ, доступных для поиска, в формате JSON.
    Учитывает настройки платформ (активна или нет).
    """
    # Формируем список платформ, которые активны
    platforms = [
        {"type": key, "name": entry["name"]}
        for key, entry in PLATFORM_REGISTRY.items()
        if platform_configs.get(key, {}).get("active", entry["active_by_default"])
    ]
    logger.info(f"Возвращаю список платформ для поиска: {platforms}")
    return jsonify(platforms)

# Функция для объединения результатов поиска
def combine_search_results(results_list):
    combined_results = []
    for results in results_list:
        if results:
            combined_results.extend(results)
    return combined_results

# Обновление маршрута для частичного поиска
@app.route("/search_partial", methods=["POST"])
def search_partial():
    data = request.get_json()
    platform_type = data.get('platform')
    search_params = session.get('search_params', {})
    name = search_params.get('name')
    city = search_params.get('city')
    phone = search_params.get('phone')
    platform_type = platform_type.lower() if platform_type else None
    if platform_type in PLATFORM_REGISTRY and platform_configs.get(platform_type, {}).get("active", PLATFORM_REGISTRY[platform_type]["active_by_default"]):
        results, error = handle_search(name, city, phone, platform_type)
        if error:
            return jsonify({"status": error, "results": []}), 200
        serialized_results = serialize_result(results)
        combined_results = combine_search_results([serialized_results])
        return jsonify({"status": f"Просматриваем {PLATFORM_REGISTRY[platform_type]['name']}...", "results": combined_results})
    return jsonify({"status": "Платформа не найдена или неактивна", "results": []}), 404

# Обновление маршрута для загрузки изображений
@app.route("/upload_image", methods=["GET", "POST"])
def upload_image():
    if request.method == "POST":
        file = request.files["file"]
        filename = handle_image_upload(file)
        if filename:
            return redirect(url_for("view_result", filename=filename))
    return render_template("upload_image.html")

# Страница отображения результата обработки изображения
@app.route("/result/<filename>")
def view_result(filename):
    """
    Отображает страницу с результатами обработки изображения (result.html).
    Извлекает EXIF-данные и генерирует HTML для карты (если есть координаты).
    """
    logger.info(f"Открываю страницу результата для файла: {filename}")
    try:
        # Проверяем, существует ли файл
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if not os.path.exists(file_path):
            logger.error(f"Файл {filename} не найден по пути {file_path}.")
            flash(f"File {filename} not found.")
            return redirect(url_for("upload_image"))
        logger.info("Извлекаю EXIF-данные из базы данных...")
        exif_data = get_image_by_filename(filename)
        if exif_data is None:
            # Если данных нет в базе, извлекаем их напрямую
            logger.warning("EXIF-данные не найдены в базе. Пробую извлечь напрямую...")
            exif_data = extract_exif_with_exiftool(file_path)
        # Проверяем, есть ли EXIF-данные в сессии
        session_exif = session.get('exif_data', None)
        if session_exif:
            logger.info("Нашёл EXIF-данные в сессии. Использую их.")
            exif_data = session_exif
        logger.info("Обрабатываю изображение и генерирую карту...")
        # Обрабатываем изображение и получаем HTML для карты
        exif_data, map_html = exif_processor.process_image(file_path, exif_data)
        # Удаляем EXIF-данные из сессии
        session.pop('exif_data', None)
        logger.info("Очистил EXIF-данные из сессии. Отображаю результат.")
        return render_template("result.html", filename=f"uploads/{filename}", exif_data=exif_data, map_html=map_html)
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения {filename}: {str(e)}")
        flash(f"Error processing image: {str(e)}")
        return redirect(url_for("upload_image"))

# Страница истории загруженных изображений
@app.route("/history")
def history():
    """
    Отображает страницу с историей загруженных изображений (history.html).
    Получает список изображений из базы данных.
    """
    logger.info("Открываю страницу истории загруженных изображений.")
    try:
        images = get_image_history(app.config["UPLOAD_FOLDER"])
        logger.info(f"Нашёл {len(images)} записей в истории.")
        return render_template("history.html", images=images)
    except Exception as e:
        logger.error(f"Ошибка при загрузке истории: {str(e)}")
        flash(f"Error loading history: {str(e)}")
        return render_template("history.html", images=[])

# API-метод для переключения активности платформы
@app.route('/toggle_platform', methods=['POST'])
def toggle_platform_endpoint():
    """
    Переключает состояние платформы (активна/неактивна) на основе запроса.
    Возвращает результат в формате JSON.
    """
    # Получаем данные из запроса
    data = request.get_json()
    platform = data.get('platform')
    state = bool(data.get('state'))
    logger.info(f"Получил запрос на переключение платформы {platform} в состояние {state}.")
    # Переключаем платформу
    if toggle_platform(platform, state):
        logger.info(f"Успешно переключил платформу {platform} в состояние {state}.")
        return jsonify({"success": True, "message": f"Platform {platform} toggled to {state}"})
    logger.error(f"Не удалось переключить платформу {platform}: платформа не найдена.")
    return jsonify({"success": False, "message": "Invalid platform"}), 400

# API-метод для отладки базы данных
@app.route("/debug/db")
def debug_db_endpoint():
    """
    Возвращает содержимое базы данных для отладки.
    """
    logger.info("Запрашиваю содержимое базы данных для отладки...")
    result = debug_db()
    logger.info(f"Получил данные из базы: {result}")
    return f"Database contents: {result}"

# Запуск приложения
if __name__ == "__main__":
    # Проверяем, существует ли папка для загрузок
    logger.info(f"Проверяю наличие папки для загрузок: {app.config['UPLOAD_FOLDER']}")
    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        logger.info("Папка для загрузок не найдена. Создаю новую...")
        os.makedirs(app.config["UPLOAD_FOLDER"])
    # Инициализируем базу данных
    logger.info("Инициализирую базу данных...")
    init_db()
    # Запускаем сервер
    logger.info("Запускаю сервер на http://0.0.0.0:5000...")
    app.run(debug=True, host="0.0.0.0", port=5000)