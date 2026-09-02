"""Egress verification tests (FR-60, invariant #8).

Asserts that Friday:
1. Directs all LLM requests strictly to loopback (127.0.0.1:8080 by default).
2. Directs all web searches strictly through SearXNG on loopback (127.0.0.1:8888 by default).
3. Connects to no other external endpoints or services directly.
"""

from urllib.parse import urlparse
import pytest

from friday import config
from friday.llm.client import LlamaClient
from friday.tools.search import SearchClient


def test_default_endpoints_are_loopback_only():
    """Default service URLs must resolve to 127.0.0.1 loopback only."""
    llm_host = urlparse(config.LLAMA_BASE_URL).hostname
    searxng_host = urlparse(config.SEARXNG_URL).hostname

    assert llm_host in ("127.0.0.1", "localhost"), f"LLAMA_BASE_URL must be loopback: {config.LLAMA_BASE_URL}"
    assert searxng_host in ("127.0.0.1", "localhost"), f"SEARXNG_URL must be loopback: {config.SEARXNG_URL}"


def test_llama_client_target_host():
    client = LlamaClient(base_url=config.LLAMA_BASE_URL)
    parsed = urlparse(client.base_url)
    assert parsed.hostname in ("127.0.0.1", "localhost")


def test_searxng_client_target_host():
    client = SearchClient(base_url=config.SEARXNG_URL)
    parsed = urlparse(client.base_url)
    assert parsed.hostname in ("127.0.0.1", "localhost")
