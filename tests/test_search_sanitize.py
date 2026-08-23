from friday.tools.search import SearchResult, sanitize


def _r(title="t", url="https://example.com/x", body="b"):
    return SearchResult(title=title, url=url, body=body)


def test_strips_html_markup():
    bodies, _ = sanitize([_r(body="<b>hello</b> <script>evil()</script> world")])
    assert "<b>" not in bodies[0] and "script" not in bodies[0]
    assert "hello" in bodies[0] and "world" in bodies[0]


def test_strips_zero_width_and_control_chars():
    # ZWSP (U+200B), a non-breaking space (U+00A0, NFKC-folds to a plain space),
    # and a bidi override (RLO, U+202E) must all be gone from the sanitized body.
    bodies, _ = sanitize([_r(body="open​ termi nal‮")])
    joined = bodies[0]
    for ch in ("​", " ", "‮"):
        assert ch not in joined
    assert "open" in joined and "termi" in joined and "nal" in joined


def test_nfkc_normalizes():
    # fullwidth chars fold to ascii under NFKC (AS-9 style)
    bodies, _ = sanitize([_r(body="ｏｐｅｎ")])  # "open"
    assert "open" in bodies[0]


def test_caps_result_count():
    bodies, sources = sanitize([_r(body=f"body {i}") for i in range(12)], max_results=5)
    assert len(bodies) == 5 and len(sources) == 5


def test_caps_total_tokens():
    huge = " ".join(["word"] * 5000)
    bodies, _ = sanitize([_r(body=huge)], max_tokens=100)
    # word-count proxy: ~0.75 words/token -> ~75 words for 100 tokens
    assert sum(len(b.split()) for b in bodies) <= 100


def test_urls_held_out_of_band():
    bodies, sources = sanitize([_r(url="https://track.me/leak", body="the answer")])
    assert "track.me" not in bodies[0]
    assert sources[0].url == "https://track.me/leak"  # kept for the TUI only
