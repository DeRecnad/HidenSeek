# exif_processor.py

import folium  # Библиотека для создания интерактивных карт
import json  # Для работы с JSON-данными
import os  # Для работы с файловой системой
import requests  # Для выполнения HTTP-запросов
from PIL import Image  # Библиотека Pillow для обработки изображений
from io import BytesIO  # Для работы с потоками данных в памяти
import pillow_heif  # Для работы с HEIC-файлами
from exiftool import ExifToolHelper  # Для извлечения метаданных с помощью ExifTool

# Импортируем функцию save_image из database.py для сохранения данных в БД
from database import save_image

# Импортируем настроенный логгер из log_config.py для ведения логов
from log_config import logger

def process_image(file_path, exif_data=None):
    """
    Обрабатывает EXIF-данные изображения и создаёт карту на основе GPS-координат.
    Если координаты найдены, создаётся HTML-код карты с помощью Folium.
    Параметры:
        file_path (str): Путь к файлу изображения.
        exif_data (dict): Словарь с EXIF-данными (если None, используется пустой словарь).
    Возвращает:
        tuple: (dict, str) - EXIF-данные и HTML-код карты (или сообщение об ошибке).
    """
    # Если exif_data не передан, инициализируем пустой словарь
    if exif_data is None:
        exif_data = {}
    logger.info(f"Processing EXIF data for file: {file_path}, EXIF: {exif_data}")

    # Инициализируем переменные для хранения координат и их направлений
    latitude = None
    longitude = None
    lat_ref = None
    lon_ref = None

    # Возможные ключи для GPS-координат из exiftool (разные форматы в зависимости от источника)
    gps_keys = {
        "GPSLatitude": "GPSLatitudeRef",
        "GPSLongitude": "GPSLongitudeRef",
        "GPS Latitude": "GPSLatitudeRef",
        "GPS Longitude": "GPSLongitudeRef",
        "Composite:GPSLatitude": "Composite:GPSLatitudeRef",
        "Composite:GPSLongitude": "Composite:GPSLongitudeRef"
    }

    # Поиск GPS-координат в EXIF-данных
    logger.debug(f"Searching for GPS coordinates in EXIF data...")
    for lat_key, ref_key in gps_keys.items():
        lon_key = lat_key.replace("Latitude", "Longitude")
        if lat_key in exif_data and lon_key in exif_data:
            latitude = exif_data[lat_key]
            longitude = exif_data[lon_key]
            lat_ref = exif_data.get(ref_key, "N")  # По умолчанию "N" (север)
            lon_ref = exif_data.get(ref_key.replace("Latitude", "Longitude"), "E")  # По умолчанию "E" (восток)
            logger.info(f"Found coordinates with keys: Latitude={lat_key}, Longitude={lon_key}, LatRef={lat_ref}, LonRef={lon_ref}")
            break

    # Если координаты не найдены, возвращаем сообщение об отсутствии данных
    if not latitude or not longitude:
        logger.warning(f"No valid GPS data found in EXIF data for file: {file_path}")
        return exif_data, "<p>No GPS data available. This may be due to location services being disabled on your device during capture or metadata being stripped during export.</p>"

    logger.debug(f"Raw coordinates: Latitude={latitude}, Longitude={longitude}, LatRef={lat_ref}, LonRef={lon_ref}")

    # Функция для преобразования координат в десятичный формат
    def convert_to_degrees(value, ref):
        """
        Преобразует GPS-координаты из формата "градусы минуты секунды" в десятичный формат.
        Параметры:
            value (str/float): Значение координаты (может быть числом или строкой в формате "58 deg 2' 51.37\"").
            ref (str): Направление координаты ("N", "S", "E", "W").
        Возвращает:
            float: Десятичное значение координаты (или None при ошибке).
        """
        try:
            # Если значение уже в десятичном формате
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace(".", "").replace("-", "").isdigit()):
                decimal = float(value)
            else:
                # Парсим формат "58 deg 2' 51.37\" N"
                parts = value.replace("deg", "").replace("'", "").replace('"', "").strip().split()
                if len(parts) == 3:
                    degrees = float(parts[0])
                    minutes = float(parts[1]) / 60
                    seconds = float(parts[2]) / 3600
                    decimal = degrees + minutes + seconds
                else:
                    raise ValueError("Unexpected coordinate format")
            # Учитываем направление (юг или запад — отрицательные значения)
            if ref in ["S", "W"]:
                decimal = -decimal
            logger.debug(f"Converted {value} ({ref}) to {decimal}")
            return decimal
        except Exception as e:
            logger.error(f"Error converting coordinates {value} ({ref}): {str(e)}")
            return None

    # Преобразуем координаты в десятичный формат
    latitude = convert_to_degrees(latitude, lat_ref)
    longitude = convert_to_degrees(longitude, lon_ref)
    logger.info(f"Calculated coordinates: Latitude={latitude}, Longitude={longitude}")

    # Создаём карту, если координаты успешно преобразованы
    map_html = "<p>No GPS data available. This may be due to location services being disabled on your device during capture or metadata being stripped during export.</p>"
    if latitude is not None and longitude is not None:
        try:
            # Создаём карту с помощью Folium, центрируя её на найденных координатах
            m = folium.Map(location=[latitude, longitude], zoom_start=15)
            # Добавляем маркер с координатами
            folium.Marker([latitude, longitude], popup="Location").add_to(m)
            # Преобразуем карту в HTML-код
            map_html = m._repr_html_()
            logger.info(f"Map generated for coordinates: Latitude={latitude}, Longitude={longitude}")
        except Exception as e:
            logger.error(f"Error generating map for file {file_path}: {str(e)}")
            map_html = f"<p>Error generating map: {str(e)}</p>"

    return exif_data, map_html

def extract_exif_with_exiftool(file_path):
    """
    Извлекает метаданные изображения с помощью ExifTool.
    Параметры:
        file_path (str): Путь к файлу изображения.
    Возвращает:
        dict: Словарь с метаданными или пустой словарь при ошибке.
    """
    try:
        # Путь к исполняемому файлу ExifTool (должен быть настроен)
        exiftool_path = "exiftool/exiftool.exe"
        # Используем ExifToolHelper для извлечения метаданных
        with ExifToolHelper(executable=exiftool_path) as et:
            metadata = et.get_metadata(file_path)[0]
            logger.info(f"Extracted metadata with ExifTool for file {file_path}: {metadata}")
            return metadata
    except Exception as e:
        logger.error(f"Error extracting EXIF with ExifToolHelper for file {file_path}: {str(e)}")
        return {}

def extract_exif_from_image(url):
    """
    Извлекает EXIF-данные из изображения по URL.
    Параметры:
        url (str): URL изображения.
    Возвращает:
        dict: Словарь с EXIF-данными или пустой словарь при ошибке.
    """
    try:
        # Отправляем HTTP-запрос для загрузки изображения
        logger.debug(f"Sending request to download image from URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        # Открываем изображение с помощью Pillow
        image = Image.open(BytesIO(response.content))
        exif_data = {}
        # Проверяем наличие EXIF-данных
        if hasattr(image, "_getexif"):
            raw_exif = image._getexif()
            if raw_exif:
                # Извлекаем и преобразуем EXIF-теги
                for tag, value in raw_exif.items():
                    tag_name = Image.ExifTags.TAGS.get(tag, tag)
                    exif_data[tag_name] = value
        logger.info(f"Extracted EXIF data from URL {url}: {exif_data}")
        return exif_data
    except Exception as e:
        logger.error(f"Error extracting EXIF from URL {url}: {str(e)}")
        return {}

def convert_heic_to_jpeg(file, filename, upload_folder="static/uploads"):
    """
    Конвертирует HEIC-файл в JPEG и извлекает его EXIF-данные.
    Параметры:
        file (FileStorage): Файл в формате HEIC.
        filename (str): Имя файла.
        upload_folder (str): Папка для сохранения файлов (по умолчанию "static/uploads").
    Возвращает:
        tuple: (str, dict) - имя нового файла (JPEG) и EXIF-данные.
    Исключения:
        Выбрасывает исключение при ошибке конвертации.
    """
    try:
        # Формируем путь для временного файла
        temp_path = os.path.join(upload_folder, f"temp_{filename}")
        # Сохраняем HEIC-файл временно
        file.seek(0)
        with open(temp_path, 'wb') as f:
            f.write(file.read())
        logger.debug(f"Saved temporary HEIC file: {temp_path}")

        # Извлекаем EXIF-данные из временного файла
        exif_data = extract_exif_with_exiftool(temp_path)
        file.seek(0)

        # Читаем HEIC-файл с помощью pillow_heif
        heif_file = pillow_heif.read_heif(file)
        # Конвертируем HEIC в объект Pillow Image
        image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
            heif_file.mode,
            heif_file.stride,
        )

        # Формируем имя нового файла (заменяем расширение на .jpg)
        new_filename = os.path.splitext(filename)[0] + ".jpg"
        file_path = os.path.join(upload_folder, new_filename)
        # Сохраняем изображение в формате JPEG
        image.save(file_path, "JPEG", quality=95)
        logger.info(f"Converted HEIC to JPEG: {file_path}")

        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Removed temporary file: {temp_path}")

        return new_filename, exif_data
    except Exception as e:
        # Удаляем временный файл при ошибке
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Removed temporary file due to error: {temp_path}")
        logger.error(f"Error converting HEIC to JPEG for file {filename}: {str(e)}")
        raise