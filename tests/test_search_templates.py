from friday.ui import templates


def test_search_templates_exist_and_are_plain():
    for s in (templates.SEARCH_LOCAL_MODE,
              templates.SEARCH_UNAVAILABLE,
              templates.SEARCH_NO_RESULTS):
        assert isinstance(s, str) and s
        assert "http" not in s  # never speak a URL
    assert "local mode" in templates.SEARCH_LOCAL_MODE.lower()
