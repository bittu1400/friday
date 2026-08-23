"""Application-side plan validation — fail closed to action=none (ADR-006).

The grammar narrows what the model can emit; this narrows it further and,
crucially, is the ONLY line of defence for adversarial input that bypasses
the model entirely (the AS-* suite is fed straight in here). Every failure
raises `SchemaError`; the caller maps that to action=none / E_SCHEMA and
never dispatches (invariant #5).

Rules (architecture.md §5.2):
    parse once, no eval, no regex cleanup
    reject unknown top-level fields
    reject duplicate keys
    reject params not in the registry's param_schema for the chosen action
    reject non-string param values (a nested object is not a string)
    normalize Unicode (NFKC); reject confusables in enum positions

`thought` was removed at G3 (OQ-08 / ADR-011): the only legal top-level
field is `action`.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from .schema import PARAM_SCHEMA


class SchemaError(Exception):
    """Raised on any validation failure. The caller fails closed to none."""


@dataclass(frozen=True)
class Plan:
    name: str
    params: Mapping[str, str]


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """json object hook that rejects duplicate keys (AS-5) instead of
    silently keeping the last one, which is CPython's default."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise SchemaError(f"duplicate key: {key!r}")
        seen[key] = value
    return seen


def validate(raw: str) -> Plan:
    """Parse and validate a raw model output string into a `Plan`.

    Raises `SchemaError` on anything malformed or out of policy.
    """
    try:
        obj = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (json.JSONDecodeError, SchemaError) as exc:
        # AS-1 (fenced), AS-2 (prefix), AS-3 (truncated) all land here: the
        # payload is not exactly one JSON object. We do NOT strip fences or
        # hunt for a brace — that is the regex cleanup the design forbids.
        if isinstance(exc, SchemaError):
            raise
        raise SchemaError(f"not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise SchemaError("top level is not an object")

    # Unknown top-level fields (AS-4). `action` is the only legal field.
    extra = set(obj) - {"action"}
    if extra:
        raise SchemaError(f"unknown top-level field(s): {sorted(extra)}")

    if "action" not in obj:
        raise SchemaError("missing 'action'")
    action = obj["action"]
    if action is None:  # AS-12: valid JSON, null action
        raise SchemaError("action is null")
    if not isinstance(action, dict):
        raise SchemaError("action is not an object")

    action_extra = set(action) - {"name", "params"}
    if action_extra:
        raise SchemaError(f"unknown action field(s): {sorted(action_extra)}")

    name = action.get("name")
    if not isinstance(name, str):
        raise SchemaError("action.name missing or not a string")
    if name not in PARAM_SCHEMA:  # AS-6: name not in the enum
        raise SchemaError(f"unknown action name: {name!r}")

    params_in = action.get("params", {})
    if not isinstance(params_in, dict):
        raise SchemaError("action.params is not an object")

    params = _validate_params(name, params_in)
    return Plan(name=name, params=params)


def _validate_params(name: str, params_in: dict[str, Any]) -> dict[str, str]:
    spec = PARAM_SCHEMA[name]

    unknown = set(params_in) - set(spec)
    if unknown:  # e.g. AS-7/AS-8 arrive as an app value, caught below, but a
        # stray key is rejected here too.
        raise SchemaError(f"unknown param(s) for {name}: {sorted(unknown)}")

    missing = set(spec) - set(params_in)
    if missing:
        raise SchemaError(f"missing param(s) for {name}: {sorted(missing)}")

    out: dict[str, str] = {}
    for key, rule in spec.items():
        value = params_in[key]
        if not isinstance(value, str):  # AS-11: nested object where str required
            raise SchemaError(f"param {name}.{key} is not a string")
        value = unicodedata.normalize("NFKC", value)
        if rule["kind"] == "enum":
            # AS-7 "/bin/sh", AS-8 "browser; rm -rf ~", AS-9 confusables:
            # none of these are members of the closed set, so all reject.
            if value not in rule["values"]:
                raise SchemaError(
                    f"param {name}.{key}={value!r} not in enum {rule['values']}"
                )
        else:  # "text"
            if value == "":
                raise SchemaError(f"param {name}.{key} is empty")
        out[key] = value
    return out
