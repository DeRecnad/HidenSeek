# log_config.py

import logging

# Настройка уровня логирования
LOG_LEVEL = logging.INFO  # Можно настроить: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Настройка формата и обработчика
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Вывод в консоль
    ]
)

# Создаём логгер
logger = logging.getLogger(__name__)

# Пример: можно добавить запись в файл, если нужно
# file_handler = logging.FileHandler('app.log')
# file_handler.setLevel(LOG_LEVEL)
# logger.addHandler(file_handler)

# logging.DEBUG — все детали.
# logging.INFO — только ключевые события.
# logging.WARNING или выше — только ошибки.