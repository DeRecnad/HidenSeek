from search_engine import PLATFORM_REGISTRY

# Конфигурация платформ (только активность и имя)
platform_configs = {
    "vk": {"active": True},
    "telegram": {"active": True},
    "instagram": {"active": False},
    "web": {"active": False}
}

# Функция для переключения активности платформы
def toggle_platform(platform, state):
    platform = platform.lower()
    if platform in PLATFORM_REGISTRY:
        platform_configs.setdefault(platform, {})["active"] = state
        return True
    return False