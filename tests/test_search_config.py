from friday import config


def test_search_defaults():
    assert config.SEARXNG_URL == "http://127.0.0.1:8888"
    assert config.SEARCH_TIMEOUT_S == 8.0          # FR-64
    assert config.SEARCH_MAX_RESULTS == 5          # FR-62
    assert config.SEARCH_MAX_TOKENS == 1500        # FR-62
    assert config.SEARCH_CONNECTED_DEFAULT is True  # ADR-046


def test_searxng_url_is_loopback():
    # invariant #8: the only egress is via a loopback address
    assert config.SEARXNG_URL.startswith("http://127.0.0.1")
