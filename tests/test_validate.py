"""Positive validation cases — a validator that rejects everything would
pass the adversarial suite trivially. These prove it accepts well-formed
plans and normalizes as intended."""

from __future__ import annotations

import pytest

from friday.llm.validate import Plan, SchemaError, validate


def test_open_app_accepted() -> None:
    p = validate('{"action":{"name":"open_app","params":{"app":"browser"}}}')
    assert p == Plan(name="open_app", params={"app": "browser"})


def test_thought_field_now_rejected() -> None:
    # thought was removed at G3 (OQ-08 / ADR-011); it is now an unknown
    # top-level field and must fail closed.
    with pytest.raises(SchemaError):
        validate('{"thought":"hi","action":{"name":"none","params":{}}}')


def test_none_with_empty_params() -> None:
    assert validate('{"action":{"name":"none","params":{}}}').name == "none"


def test_text_param_accepted_verbatim() -> None:
    p = validate('{"action":{"name":"web_search","params":{"query":"weather in Pune"}}}')
    assert p.params["query"] == "weather in Pune"


def test_missing_required_param_rejected() -> None:
    with pytest.raises(SchemaError):
        validate('{"action":{"name":"open_app","params":{}}}')


def test_extra_param_rejected() -> None:
    with pytest.raises(SchemaError):
        validate('{"action":{"name":"none","params":{"app":"browser"}}}')
