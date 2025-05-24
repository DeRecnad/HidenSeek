# database.py

import sqlite3
import json
from datetime import datetime
import os

# Импортируем настроенный логгер из log_config.py для ведения логов
from log_config import logger

def init_db():
    """
    Инициализирует базу данных SQLite с таблицей images, если она ещё не существует.
    Создаёт таблицу с полями: id, filename, timestamp и exif_data.
    Параметры:
        None
    Возвращает:
        None
    Исключения:
        Логируются ошибки при создании базы данных.
    """
    try:
        conn = sqlite3.connect("osint.db")
        cursor = conn.cursor()
        # Создаём таблицу images, если она не существует
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                exif_data TEXT
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")

def save_image(image_id, filename, exif_data):
    """
    Сохраняет информацию об изображении в базе данных.
    Параметры:
        image_id (int): Уникальный идентификатор изображения.
        filename (str): Имя файла изображения.
        exif_data (dict): Данные EXIF в формате словаря (или None).
    Возвращает:
        tuple: (bool, str) - успех операции и сообщение об ошибке (если есть).
    """
    try:
        conn = sqlite3.connect("osint.db")
        cursor = conn.cursor()
        # Форматируем текущую дату и время
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Преобразуем exif_data в JSON-строку для хранения
        exif_str = json.dumps(exif_data) if exif_data else ""
        # Выполняем вставку записи в таблицу
        cursor.execute("INSERT INTO images (id, filename, timestamp, exif_data) VALUES (?, ?, ?, ?)",
                       (image_id, filename, timestamp, exif_str))
        conn.commit()
        conn.close()
        logger.info(f"Saved image to database: id={image_id}, filename={filename}")
        return True, None
    except Exception as e:
        logger.error(f"Error saving image to database: {str(e)}")
        return False, f"Error saving image: {str(e)}"

def get_image_by_filename(filename):
    """
    Извлекает данные EXIF изображения по его имени файла из базы данных.
    Параметры:
        filename (str): Имя файла изображения.
    Возвращает:
        dict: Данные EXIF (распарсенные из JSON) или None, если данные не найдены.
    """
    try:
        conn = sqlite3.connect("osint.db")
        cursor = conn.cursor()
        # Выполняем запрос к базе данных
        cursor.execute("SELECT exif_data FROM images WHERE filename = ?", (filename,))
        result = cursor.fetchone()
        conn.close()
        # Возвращаем распарсенные данные или None
        return json.loads(result[0]) if result and result[0] else None
    except Exception as e:
        logger.error(f"Error retrieving image from database: {str(e)}")
        return None

def get_image_history(upload_folder="static/uploads"):
    """
    Получает историю загруженных изображений с их метаданными, отсортированную по времени.
    Параметры:
        upload_folder (str): Путь к папке с загруженными файлами (по умолчанию "static/uploads").
    Возвращает:
        list: Список словарей с данными об изображениях (id, filename, timestamp, exif_data).
    """
    try:
        conn = sqlite3.connect("osint.db")
        cursor = conn.cursor()
        # Получаем все записи, отсортированные по убыванию времени
        cursor.execute("SELECT id, filename, timestamp, exif_data FROM images ORDER BY timestamp DESC")
        images_raw = cursor.fetchall()
        conn.close()
        images = []
        for image in images_raw:
            image_id, filename, timestamp, exif_json = image
            # Распаковываем JSON-строку в словарь
            exif_data = json.loads(exif_json) if exif_json else {}
            # Формируем полный путь к файлу
            file_path = os.path.join(upload_folder, filename)
            # Проверяем существование файла
            if os.path.exists(file_path):
                images.append({
                    "id": image_id,
                    "filename": f"uploads/{filename}",  # Относительный путь для фронтенда
                    "timestamp": timestamp,
                    "exif_data": exif_data
                })
        logger.info(f"Retrieved image history: {len(images)} images found.")
        return images
    except Exception as e:
        logger.error(f"History error: {str(e)}")
        return []

def debug_db():
    """
    Выполняет отладочный вывод содержимого таблицы images.
    Используется для проверки состояния базы данных.
    Параметры:
        None
    Возвращает:
        list: Список строк таблицы или строку с ошибкой.
    """
    try:
        conn = sqlite3.connect("osint.db")
        cursor = conn.cursor()
        # Получаем все записи из таблицы
        cursor.execute("SELECT * FROM images")
        rows = cursor.fetchall()
        conn.close()
        logger.debug(f"Debug DB result: {len(rows)} rows retrieved.")
        return rows
    except Exception as e:
        logger.error(f"Error accessing database: {str(e)}")
        return f"Error accessing database: {str(e)}"