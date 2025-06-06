import requests
import logging
from datetime import datetime
from config import VK_ACCESS_TOKEN
from search_engine import register_platform

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search_vk_by_api(username, access_token):
    """Поиск профилей ВКонтакте через API"""
    try:
        # Удаляем @ если есть
        username = username.replace('@', '')
        
        # Формируем URL для API
        api_url = "https://api.vk.com/method/users.get"
        
        # Параметры запроса
        params = {
            'user_ids': username,
            'fields': 'activities,about,books,bdate,career,connections,contacts,city,domain,education,exports,first_name,last_name,interests,last_seen,maiden_name,military,movies,music,nickname,occupation,personal,photo_max,quotes,relation,relatives,schools,site,status,universities,photo_50,photo_100,photo_200,photo_400,photo_max_orig,sex,home_town,online,timezone,tv,games,is_verified,verified',
            'access_token': access_token,
            'v': '5.131'  # Версия API
        }
        
        # Выполняем запрос
        response = requests.get(api_url, params=params, timeout=10)
        logger.info(f"Код ответа API: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Не удалось получить профиль через API: {response.status_code}")
            return None
            
        data = response.json()
        
        if 'error' in data:
            logger.error(f"Ошибка API: {data['error']}")
            return None
            
        if not data.get('response'):
            logger.error("Нет данных в ответе API")
            return None
            
        user_data = data['response'][0]
        
        # Получаем время последнего посещения и форматируем его
        last_seen = user_data.get("last_seen", {}).get("time")
        last_seen_formatted = None
        if last_seen:
            last_seen_time = datetime.fromtimestamp(last_seen).strftime("%H:%M, %d %b %Y")
            platform_map = {1: "мобильное устройство", 4: "iPhone", 7: "браузер"}
            platform = platform_map.get(user_data.get("last_seen", {}).get("platform"), "неизвестное устройство")
            last_seen_formatted = f"{last_seen_time} ({platform})"
        
        # Формируем результат
        result = {
            'platform': 'vk',
            'timestamp': datetime.now().strftime("%m.%Y"),
            'id': user_data.get('id'),
            'domain': user_data.get('domain'),
            'full_name': f"{user_data.get('first_name', 'Без имени')} {user_data.get('last_name', '')}".strip(),
            'screen_name': user_data.get('screen_name'),
            'sex': "мужской" if user_data.get("sex") == 2 else "женский" if user_data.get("sex") == 1 else "не указан",
            'bdate': user_data.get('bdate'),
            'status': user_data.get('status'),
            'city': user_data.get('city', {}).get('title') if user_data.get('city') else "Неизвестно",
            'home_town': user_data.get('home_town'),
            'last_seen': last_seen_formatted,
            'online': "В сети" if user_data.get('online') == 1 else "Не в сети",
            'photo': user_data.get('photo_200'),
            'profile_link': f"https://vk.com/{username}",
            'about': user_data.get('about'),
            'activities': user_data.get('activities'),
            'personal_info': {},
            'education': {},
            'career': [],
            'interests': {},
            'connections': {},
            'contacts': {}
        }
        
        # Личная информация
        if 'personal' in user_data:
            personal = user_data['personal']
            if 'languages' in personal:
                result['personal_info']['languages'] = personal['languages']
            if 'political' in personal:
                result['personal_info']['political_views'] = personal['political']
            if 'religion' in personal:
                result['personal_info']['worldview'] = personal['religion']
            if 'life_main' in personal:
                result['personal_info']['life_priority'] = personal['life_main']
            if 'people_main' in personal:
                result['personal_info']['people_priority'] = personal['people_main']
            if 'smoking' in personal:
                result['personal_info']['smoking'] = personal['smoking']
            if 'alcohol' in personal:
                result['personal_info']['alcohol'] = personal['alcohol']
                
        # Образование
        if 'education' in user_data:
            education = user_data['education']
            if 'university' in education:
                result['education']['university'] = education['university']
            if 'university_name' in education:
                result['education']['university_name'] = education['university_name']
            if 'faculty' in education:
                result['education']['faculty'] = education['faculty']
            if 'graduation' in education:
                result['education']['graduation_year'] = education['graduation']
                
        # Школы
        if 'schools' in user_data:
            result['education']['schools'] = user_data['schools']
            
        # Карьера
        if 'career' in user_data:
            result['career'] = user_data['career']
            
        # Интересы
        if 'interests' in user_data:
            result['interests']['interests'] = user_data['interests']
        if 'movies' in user_data:
            result['interests']['movies'] = user_data['movies']
        if 'music' in user_data:
            result['interests']['music'] = user_data['music']
        if 'books' in user_data:
            result['interests']['books'] = user_data['books']
        if 'quotes' in user_data:
            result['interests']['quotes'] = user_data['quotes']
        if 'tv' in user_data:
            result['interests']['tv'] = user_data['tv']
        if 'games' in user_data:
            result['interests']['games'] = user_data['games']
            
        # Связи
        if 'connections' in user_data:
            result['connections'] = user_data['connections']
            
        # Контакты
        if 'contacts' in user_data:
            result['contacts'] = user_data['contacts']
            
        logger.info(f"Найдены данные через API: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при поиске профиля ВКонтакте через API: {str(e)}")
        return None

@register_platform("VK")
def vk_search(name, access_token=None, proxy=None):
    """Поиск профилей ВКонтакте через API"""
    try:
        result = search_vk_by_api(name, VK_ACCESS_TOKEN)
        if not result:
            return [], "Не удалось получить данные профиля"
            
        # Форматирование карьеры
        if result['career']:
            career_list = []
            for job in result['career']:
                career_item = []
                if 'position' in job:
                    career_item.append(f"Должность: {job['position']}")
                if 'company' in job:
                    career_item.append(f"Компания: {job['company']}")
                if 'from' in job:
                    career_item.append(f"С: {job['from']}")
                if 'until' in job:
                    career_item.append(f"По: {job['until']}")
                career_list.append(" | ".join(career_item))
            result['career'] = "<br>".join(career_list)

        # Форматирование образования
        if result['education']:
            education_list = []
            
            if 'university_name' in result['education']:
                education_list.append(f"Университет: {result['education']['university_name']}")
            if 'faculty' in result['education']:
                education_list.append(f"Факультет: {result['education']['faculty']}")
            if 'graduation_year' in result['education']:
                education_list.append(f"Год выпуска: {result['education']['graduation_year']}")
            
            if 'schools' in result['education']:
                schools_list = []
                for school in result['education']['schools']:
                    school_info = []
                    if 'name' in school:
                        school_info.append(f"Школа: {school['name']}")
                    if 'year_from' in school:
                        school_info.append(f"С: {school['year_from']}")
                    if 'year_to' in school:
                        school_info.append(f"По: {school['year_to']}")
                    if 'year_graduated' in school:
                        school_info.append(f"Выпуск: {school['year_graduated']}")
                    schools_list.append(" | ".join(school_info))
                if schools_list:
                    education_list.append("Школы:")
                    education_list.extend(schools_list)
            
            result['education'] = "<br>".join(education_list)

        # Форматирование интересов
        if result['interests']:
            interests = result['interests']
            interests_list = []
            
            if 'interests' in interests and interests['interests']:
                interests_list.append(f"Интересы: {interests['interests']}")
            if 'movies' in interests and interests['movies']:
                interests_list.append(f"Фильмы: {interests['movies']}")
            if 'music' in interests and interests['music']:
                interests_list.append(f"Музыка: {interests['music']}")
            if 'books' in interests and interests['books']:
                interests_list.append(f"Книги: {interests['books']}")
            if 'tv' in interests and interests['tv']:
                interests_list.append(f"Телешоу: {interests['tv']}")
            if 'games' in interests and interests['games']:
                interests_list.append(f"Игры: {interests['games']}")
            if 'quotes' in interests and interests['quotes']:
                # Разбиваем цитаты по точкам и форматируем каждую
                quotes = interests['quotes'].split('. ')
                formatted_quotes = []
                for i, quote in enumerate(quotes):
                    if quote.strip():  # Пропускаем пустые цитаты
                        # Добавляем точку только если это не последняя цитата или если она еще не заканчивается точкой
                        if i < len(quotes) - 1 or not quote.strip().endswith('.'):
                            formatted_quotes.append(quote.strip() + '.')
                        else:
                            formatted_quotes.append(quote.strip())
                interests_list.append("Цитаты:<br>" + "<br>".join(formatted_quotes))
            
            result['interests'] = "<br>".join(interests_list)
            
        # Форматирование личной информации
        if result['personal_info']:
            personal = result['personal_info']
            personal_list = []
            
            if 'languages' in personal:
                languages = personal['languages']
                if isinstance(languages, list):
                    personal_list.append("Языки:<br>" + "<br>".join(languages))
                elif isinstance(languages, str):
                    # Разбиваем языки по запятым и форматируем каждый
                    lang_list = [lang.strip() for lang in languages.split(',')]
                    personal_list.append("Языки:<br>" + "<br>".join(lang_list))
                else:
                    personal_list.append(f"Языки: {languages}")
            
            if 'political_views' in personal:
                political_views = {
                    1: "Коммунистические",
                    2: "Социалистические",
                    3: "Умеренные",
                    4: "Либеральные",
                    5: "Консервативные",
                    6: "Монархические",
                    7: "Ультраконсервативные",
                    8: "Индифферентные",
                    9: "Либертарианские"
                }
                personal_list.append(f"Политические взгляды: {political_views.get(personal['political_views'], 'Не указано')}")
            
            if 'worldview' in personal:
                personal_list.append(f"Мировоззрение: {personal['worldview']}")
            
            if 'life_priority' in personal:
                life_priority = {
                    1: "Семья и дети",
                    2: "Карьера и деньги",
                    3: "Развлечения и отдых",
                    4: "Наука и исследования",
                    5: "Совершенствование мира",
                    6: "Саморазвитие",
                    7: "Красота и искусство",
                    8: "Слава и влияние"
                }
                personal_list.append(f"Главное в жизни: {life_priority.get(personal['life_priority'], 'Не указано')}")
            
            if 'people_priority' in personal:
                people_priority = {
                    1: "Ум и креативность",
                    2: "Доброта и честность",
                    3: "Красота и здоровье",
                    4: "Власть и богатство",
                    5: "Смелость и упорство",
                    6: "Юмор и жизнелюбие"
                }
                personal_list.append(f"Главное в людях: {people_priority.get(personal['people_priority'], 'Не указано')}")
            
            if 'smoking' in personal:
                smoking = {
                    1: "Резко негативное",
                    2: "Негативное",
                    3: "Компромиссное",
                    4: "Нейтральное",
                    5: "Положительное"
                }
                personal_list.append(f"Отношение к курению: {smoking.get(personal['smoking'], 'Не указано')}")
            
            if 'alcohol' in personal:
                alcohol = {
                    1: "Резко негативное",
                    2: "Негативное",
                    3: "Компромиссное",
                    4: "Нейтральное",
                    5: "Положительное"
                }
                personal_list.append(f"Отношение к алкоголю: {alcohol.get(personal['alcohol'], 'Не указано')}")
            
            result['personal_info'] = "<br>".join(personal_list)

        # Форматирование связей
        if result.get('connections'):
            connections_list = []
            connections = result['connections']
            
            if isinstance(connections, dict):
                if 'skype' in connections and connections['skype']:
                    connections_list.append(f"Skype: {connections['skype']}")
                if 'facebook' in connections and connections['facebook']:
                    connections_list.append(f"Facebook: {connections['facebook']}")
                if 'twitter' in connections and connections['twitter']:
                    connections_list.append(f"Twitter: {connections['twitter']}")
                if 'instagram' in connections and connections['instagram']:
                    connections_list.append(f"Instagram: {connections['instagram']}")
                if 'livejournal' in connections and connections['livejournal']:
                    connections_list.append(f"LiveJournal: {connections['livejournal']}")
            
            result['connections'] = "<br>".join(connections_list) if connections_list else "Не указано"

        # Форматирование контактов
        if result.get('contacts'):
            contacts_list = []
            contacts = result['contacts']
            
            if isinstance(contacts, dict):
                if 'mobile_phone' in contacts and contacts['mobile_phone']:
                    contacts_list.append(f"Мобильный: {contacts['mobile_phone']}")
                if 'home_phone' in contacts and contacts['home_phone']:
                    contacts_list.append(f"Домашний: {contacts['home_phone']}")
                if 'site' in contacts and contacts['site']:
                    contacts_list.append(f"Сайт: {contacts['site']}")
            
            result['contacts'] = "<br>".join(contacts_list) if contacts_list else "Не указано"
        
        return [result], None
        
    except Exception as e:
        logger.error(f"Ошибка в vk_search: {str(e)}")
        return [], str(e) 