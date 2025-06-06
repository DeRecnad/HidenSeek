// Инициализация скрипта после полной загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    console.log("JavaScript loaded successfully.");

    // Переключение видимости метаданных
    const toggleButtons = document.querySelectorAll('.toggle-btn');
    toggleButtons.forEach(button => {
        // Обработчик клика для кнопки переключения
        button.addEventListener('click', function() {
            // Находим следующий элемент после кнопки (метаданные)
            const metadataContent = this.nextElementSibling;
            if (metadataContent) {
                // Переключаем класс 'show' для отображения/скрытия метаданных
                metadataContent.classList.toggle('show');
                // Обновляем текст кнопки в зависимости от состояния
                this.textContent = metadataContent.classList.contains('show') ? 'Hide' : 'Show';
            } else {
                // Логируем ошибку, если метаданные не найдены
                console.error("Metadata content not found for toggle button:", this);
            }
        });
    });

    // Обработка выбора файла (для upload_image.html)
    const fileInput = document.getElementById('file');
    const fileNameDisplay = document.getElementById('file-name');
    const previewContainer = document.getElementById('preview');

    if (fileInput && fileNameDisplay && previewContainer) {
        // Обработчик изменения выбранного файла
        fileInput.addEventListener('change', function() {
            // Получаем первый выбранный файл
            const file = this.files[0];
            if (file) {
                // Отображаем имя файла
                fileNameDisplay.textContent = file.name;
                if (file.type.startsWith('image/')) {
                    // Создаём объект для чтения файла как данных URL
                    const reader = new FileReader();
                    // Обработчик успешной загрузки файла для предпросмотра
                    reader.onload = function(e) {
                        // Создаём элемент изображения
                        const img = document.createElement('img');
                        // Устанавливаем источник изображения из загруженных данных
                        img.src = e.target.result;
                        // Добавляем класс для стилизации
                        img.className = 'preview-image';
                        // Очищаем контейнер предпросмотра
                        previewContainer.innerHTML = '';
                        // Добавляем изображение в контейнер
                        previewContainer.appendChild(img);
                    };
                    // Читаем файл как Data URL
                    reader.readAsDataURL(file);
                } else {
                    // Сообщаем, что предпросмотр недоступен для не-изображений
                    previewContainer.innerHTML = '<p>Preview not available for this file type.</p>';
                }
            } else {
                // Сбрасываем имя файла и предпросмотр, если файл не выбран
                fileNameDisplay.textContent = 'No file selected';
                previewContainer.innerHTML = '';
            }
        });
    }

    // Валидация формы поиска (для index.html)
    const searchForm = document.getElementById('search-form');
    if (searchForm) {
        // Обработчик отправки формы поиска
        searchForm.addEventListener('submit', function(event) {
            // Получаем поле ввода телефона
            const phoneInput = document.getElementById('phone');
            const phoneValue = phoneInput ? phoneInput.value.trim() : '';
            // Регулярное выражение для проверки формата телефона (+7XXXXXXXXXX)
            const phonePattern = /^\+7[0-9]{10}$/;

            if (phoneValue && !phonePattern.test(phoneValue)) {
                // Предотвращаем отправку формы при неверном формате
                event.preventDefault();
                // Выводим сообщение об ошибке
                alert('Phone must be in format +7XXXXXXXXXX (e.g., +79504643030)');
                // Фокусируемся на поле ввода
                if (phoneInput) phoneInput.focus();
            }
        });
    }

    // Логика для advanced_search.html: переключение Instagram
    const toggleButton = document.getElementById('instagram-toggle');
    if (toggleButton) {
        // Проверяем сохранённое состояние переключателя в localStorage
        const isInstagramActive = localStorage.getItem('instagramActive') === 'true';
        // Устанавливаем начальное состояние кнопки
        toggleButton.classList.toggle('active', isInstagramActive);
        toggleButton.textContent = isInstagramActive ? 'Выключить поиск по Instagram' : 'Включить поиск по Instagram';

        // Функция для переключения состояния поиска по Instagram
        function toggleInstagram() {
            // Переключаем класс активности
            const isActive = toggleButton.classList.toggle('active');
            // Обновляем текст кнопки
            toggleButton.textContent = isActive ? 'Выключить поиск по Instagram' : 'Включить поиск по Instagram';
            // Сохраняем состояние в localStorage
            localStorage.setItem('instagramActive', isActive);

            // Отправляем запрос на сервер для изменения состояния
            fetch('/toggle_platform', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ platform: 'instagram', state: isActive })
            })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    // Возвращаем предыдущее состояние при ошибке
                    toggleButton.classList.toggle('active');
                    toggleButton.textContent = !isActive ? 'Включить поиск по Instagram' : 'Выключить поиск по Instagram';
                    localStorage.setItem('instagramActive', !isActive);
                    alert('Ошибка переключения состояния Instagram.');
                } else {
                    // Уведомляем пользователя об успешном переключении
                    alert(`Поиск по Instagram ${isActive ? 'включён' : 'выключен'}. ${isActive ? 'Убедитесь, что VPN активен!' : ''}`);
                }
            })
            .catch(error => {
                // Обрабатываем ошибки сети или сервера
                console.error('Error toggling Instagram:', error);
                toggleButton.classList.toggle('active');
                toggleButton.textContent = !isActive ? 'Включить поиск по Instagram' : 'Выключить поиск по Instagram';
                localStorage.setItem('instagramActive', !isActive);
                alert('Ошибка при переключении состояния Instagram!');
            });
        }

        // Обработчик клика для кнопки переключения Instagram
        toggleButton.addEventListener('click', toggleInstagram);
    }

    // Логика для search_results.html

    // Функция обновления статуса поиска
    function updateStatus(message) {
        const statusDiv = document.getElementById('status');
        if (statusDiv) {
            // Обновляем текст статуса
            statusDiv.textContent = message;
            // Сбрасываем опакость и применяем анимацию появления
            statusDiv.style.opacity = 0;
            statusDiv.style.animation = 'fadeIn 1s forwards';
        }
    }

    // Функция агрегации информации о пользователе
    function updateAggregatedInfo(dataArray) {
        let aggregated = {
            fullName: 'Неизвестно',
            birthDate: 'Загрузка...',
            gender: 'Загрузка...',
            age: 'Загрузка...',
            address: 'Загрузка...',
            phones: [],
            email: 'Загрузка...',
            ip: 'Загрузка...',
            education: 'Загрузка...',
            work: 'Загрузка...',
            position: 'Загрузка...'
        };

        // Обходим массив данных и агрегируем информацию
        dataArray.forEach(data => {
            // Основные данные
            if (data.full_name && data.full_name !== 'N/A' && data.full_name !== 'Неизвестно') {
                aggregated.fullName = data.full_name;
            }
            if (data.first_name && data.last_name) {
                const newFullName = `${data.first_name || ''} ${data.last_name || ''}`.trim();
                if (newFullName && newFullName !== 'Неизвестно') {
                    aggregated.fullName = newFullName;
                }
            }
            if (data.bdate && data.bdate !== 'Загрузка...') aggregated.birthDate = data.bdate;
            if (data.sex && data.sex !== 'Загрузка...') aggregated.gender = data.sex;
            if (data.age && data.age !== 'Загрузка...') aggregated.age = data.age;

            // Контактная информация
            if (data.city && data.city !== 'Загрузка...') aggregated.address = data.city;
            if (data.phone) aggregated.phones.push(data.phone);
            if (data.phones && Array.isArray(data.phones)) {
                aggregated.phones = [...new Set([...aggregated.phones, ...data.phones.filter(p => p)])];
            }
            if (data.email && data.email !== 'Загрузка...') aggregated.email = data.email;
            if (data.ip && data.ip !== 'Загрузка...') aggregated.ip = data.ip;

            // Образование и работа
            if (data.education && data.education !== 'Загрузка...') aggregated.education = data.education;
            if (data.career && data.career.length > 0) {
                const latestJob = data.career[0];
                if (latestJob.company && latestJob.company !== 'Загрузка...') aggregated.work = latestJob.company;
                if (latestJob.position && latestJob.position !== 'Загрузка...') aggregated.position = latestJob.position;
            }
        });
        
        // Обновляем элементы на странице
        const elements = {
            'full-name': aggregated.fullName,
            'birth-date': aggregated.birthDate,
            'gender': aggregated.gender,
            'age': aggregated.age,
            'address': aggregated.address,
            'phone': aggregated.phones.length > 0 ? aggregated.phones.join(', ') : 'Неизвестно',
            'email': aggregated.email,
            'ip': aggregated.ip,
            'education': aggregated.education,
            'work': aggregated.work,
            'position': aggregated.position
        };

        // Обновляем все элементы
        for (const [id, value] of Object.entries(elements)) {
            const element = document.getElementById(id);
            if (element) {
                // Обновляем только если новое значение не "Загрузка..." или "Неизвестно"
                if (value !== 'Загрузка...' && value !== 'Неизвестно') {
                    element.textContent = value;
                }
            }
        }
    }

    // Функция добавления деталей платформы в результаты поиска
    function addPlatformDetails(platformName, data) {
        const detailsDiv = document.getElementById('platform-details');
        if (!detailsDiv) return;

        // Проверяем наличие карточки для данной платформы
        let card = detailsDiv.querySelector(`.platform-card[data-platform="${platformName}"]`);
        if (!card) {
            // Создаём новую карточку, если её нет
            card = document.createElement('div');
            card.className = 'platform-card';
            card.setAttribute('data-platform', platformName);
            card.innerHTML = `<h3>${platformName}</h3><div class="platform-details"></div>`;
            detailsDiv.appendChild(card);
        }
        const details = card.querySelector('.platform-details');
        // Очищаем содержимое деталей
        details.innerHTML = '';

        if (data && data.length > 0) {
            // Обрабатываем каждый результат для данной платформы
            data.forEach(result => {
                // Специальная обработка для VK
                if (platformName === 'VK_ALT' && result.formatted_output) {
                    details.innerHTML = `<pre class="vk-profile">${result.formatted_output}</pre>`;
                    return;
                }

                for (const [key, value] of Object.entries(result)) {
                    if (value === null || value === undefined || value === '') continue;
                    if (key === 'phones' && Array.isArray(value) && value.length > 0) {
                        details.innerHTML += `<p><strong>Телефоны:</strong></p><ul class="phone-list">`;
                        value.forEach(phone => {
                            if (phone) details.innerHTML += `<li>${phone}</li>`;
                        });
                        details.innerHTML += `</ul>`;
                    } else if (key === 'last_seen' && typeof value === 'number') {
                        const date = new Date(value * 1000);
                        details.innerHTML += `<p><strong>Последний раз видели:</strong> ${date.toLocaleString()}</p>`;
                    } else if (key === 'last_seen_formatted') {
                        details.innerHTML += `<p><strong>Последний раз видели:</strong> ${value}</p>`;
                    } else if (key.match(/photo(_\d+)?|Avatar/) && value) {
                        details.innerHTML += `<p><strong>Фото (${key}):</strong> <img src="${value}" alt="Profile Photo" style="max-width: 150px;"></p>`;
                    } else {
                        details.innerHTML += `<p><strong>${key}:</strong> ${value || 'Неизвестно'}</p>`;
                    }
                }
            });
        } else {
            // Отображаем сообщение, если данные отсутствуют
            details.innerHTML = '<p>Данные не найдены.</p>';
        }
    }

    // Логика поиска для search_results.html
    let platforms = [];
    let index = 0;

    const platformDetailsDiv = document.getElementById('platform-details');
    if (platformDetailsDiv) {
        // Загрузка списка платформ для поиска
        fetch('/get_platforms')
            .then(response => response.json())
            .then(data => {
                // Сохраняем полученные платформы
                platforms = data;
                performSearch();
            })
            .catch(error => {
                console.error('Error loading platforms:', error);
                updateStatus('Ошибка загрузки платформ!');
            });

        // Функция для выполнения поиска по платформам
        function performSearch() {
            if (index >= platforms.length) {
                // Завершаем поиск, если все платформы обработаны
                updateStatus('Поиск завершён!');
                return;
            }

            const platform = platforms[index];
            // Обновляем статус текущей платформы
            updateStatus(`Просматриваем ${platform.name}...`);

            fetch('/search_partial', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ platform: platform.type })
            })
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                return response.json();
            })
            .then(data => {
                console.log(`Response for ${platform.name}:`, data);
                if (data.results && data.results.length > 0) {
                    // Обновляем агрегированную информацию и детали платформы
                    updateAggregatedInfo(data.results);
                    addPlatformDetails(platform.name, data.results);
                } else {
                    addPlatformDetails(platform.name, []);
                }
                // Переходим к следующей платформе
                index++;
                performSearch();
            })
            .catch(error => {
                console.error(`Error searching ${platform.name}:`, error);
                updateStatus(`Ошибка при поиске в ${platform.name}!`);
                addPlatformDetails(platform.name, []);
                index++;
                performSearch();
            });
        }
    }
});