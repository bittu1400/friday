from friday.tools.search import SearchResult
from friday.ui.tui import render_sources


def test_render_sources_lists_title_and_url():
    src = [SearchResult("Wikipedia", "https://en.wikipedia.org/x", "b"),
           SearchResult("BBC", "https://bbc.test/y", "b")]
    out = render_sources(src)
    assert "Wikipedia" in out and "https://en.wikipedia.org/x" in out
    assert "BBC" in out and "https://bbc.test/y" in out


def test_render_sources_empty_is_empty_string():
    assert render_sources([]) == ""
