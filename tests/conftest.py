import pytest

from hidenseek.config import Settings


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dir = tmp_path
    s.module_delay = 0.0
    s.module_retries = 2
    s.smtp_host = s.smtp_from = ""
    s.github_client_id = s.github_client_secret = s.hibp_api_key = s.github_token = ""
    return s
