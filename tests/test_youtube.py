"""Adversarial AS-13..AS-16 — the youtube_search query is THE audited
exception where model text reaches a command line (ADR-027, FR-39x). These
test the URL builder, not the plan-shape validator, so they live here
rather than in adversarial.jsonl (ADR-033). With the 12 in adversarial.jsonl
these complete the 16/16 the G3 gate requires.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from friday.errors import PolicyRejected
from friday.tools.registry import REGISTRY, youtube_url

SPEC = REGISTRY["youtube_search"]


def test_as13_shell_metacharacters_rejected() -> None:
    # `&` and `,` `.` `'` `-` are deliberately allowed (real search terms);
    # they are safe because nothing reaches a shell (argv, shell=False).
    # These carry chars outside the charset and must be rejected, not stripped.
    for q in ["lofi; rm -rf ~", "$(whoami)", "a|b", "a`b`", "x > /etc/passwd"]:
        with pytest.raises(PolicyRejected):
            youtube_url(q)


def test_as14_overlong_query_rejected() -> None:
    with pytest.raises(PolicyRejected):
        youtube_url("a" * 5000)


def test_as15_query_cannot_inject_a_second_argv_element() -> None:
    # Even a multi-word query stays a single argv element; argv is always
    # exactly [hyprctl, dispatch, exec, <browser>, <one url>].
    argv = SPEC.build_argv({"query": "lo fi jazz beats"})
    assert len(argv) == 5
    assert argv[:3] == ["hyprctl", "dispatch", "exec"]
    assert argv[4].startswith("https://www.youtube.com/results?search_query=")
    assert " " not in argv[4]  # the space was percent-encoded, not split


def test_as16_query_cannot_change_the_netloc() -> None:
    # Characters that could rewrite the netloc (@ / : //) are outside the
    # charset and rejected, not stripped.
    for q in ["evil.com/@x", "a//b", "x:8080", "@evil"]:
        with pytest.raises(PolicyRejected):
            youtube_url(q)
    # A clean query still yields exactly the youtube netloc.
    assert urlparse(youtube_url("lo-fi jazz")).netloc == "www.youtube.com"
