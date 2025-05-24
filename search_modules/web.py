from search_engine import register_platform

@register_platform("Web")
def search_web(name=None, city=None, phone=None):
    """Поиск в вебе (заглушка)."""
    return [], "Web search not implemented yet."