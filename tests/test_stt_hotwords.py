"""The hotword list must track the app enum, not Phase 1 — D31.

Twice now a Phase-1 vocabulary list has been left behind by a later gate and
the cost was paid at a microphone. D26: `STT_HOTWORDS` had no G12 words, so
"wifi" came back as wife / weapon / way / life on four consecutive turns.
D31: ADR-097 widened the app enum from 5 ids to every installed desktop entry
and left this list at the same five apps, so for a month the only application
names Whisper was biased toward were the only five that had ever been
dispatched — `action_audit` has no other `open_app` row in the life of the
project.

This test is the D24 coverage test's shape, applied to a parameter VALUE set
rather than to action names. It does not check WHICH apps are listed — that is
the owner's call and it moves — only that the list did not fall back to Phase 1.
"""

from __future__ import annotations

import re

from friday import config
from friday.llm import schema

# Owner's call 2026-09-03: twenty app names now, the remaining ~145 once the
# cost of these twenty is measured (OQ-68). Seven names matched before, so this
# floor fails on a revert to Phase 1 without pinning the exact list.
_MIN_APP_HOTWORDS = 20


def _slug(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", word.lower()).strip("_")


def test_hotwords_cover_installed_applications_not_just_the_curated_five():
    enum = set(schema.PARAM_SCHEMA["open_app"]["app"]["values"])
    matched = {
        _slug(w) for w in config.STT_HOTWORDS.split(",") if _slug(w) in enum
    }
    assert len(matched) >= _MIN_APP_HOTWORDS, (
        f"only {len(matched)} hotwords name an app in the enum "
        f"({sorted(matched)}) — a word the user must SAY to reach a capability "
        "belongs in STT_HOTWORDS (D26, D31)"
    )


def test_hotwords_still_carry_the_g12_control_vocabulary():
    """D26's own regression: the words that select an action, not an app."""

    low = config.STT_HOTWORDS.lower()
    for word in ("wifi", "brightness", "clipboard", "dictation", "workspace"):
        assert word in low, f"{word!r} missing from STT_HOTWORDS (D26)"


def test_no_hotword_is_a_near_miss_of_an_app_the_enum_cannot_serve():
    """D33. "Android Studio", "IntelliJ IDEA", "PyCharm" and "WebStorm" were all
    in this list while the enum held only `android_studio_panda_4_2025_3_4_patch_1`
    and friends — the `.desktop` Name with the release baked in. Whisper was
    being biased toward names the enum structurally could not deliver, and the
    floor test above could not see it: the count was over 20 either way.

    A hotword that is not an id but IS the prefix of one is the signature of
    exactly that — the app is there, under a name nobody says. A control word
    ("wifi", "brightness") is not a prefix of any app id, so it does not trip
    this; measured clean against the live list."""
    enum = set(schema.PARAM_SCHEMA["open_app"]["app"]["values"])

    stranded = {}
    for word in config.STT_HOTWORDS.split(","):
        s = _slug(word)
        if not s or s in enum:
            continue
        near = sorted(k for k in enum if k.startswith(s + "_"))
        if near:
            stranded[word.strip()] = near[:3]

    assert not stranded, (
        f"hotwords name apps the enum cannot serve under that name: {stranded} "
        "— the id is derived from the .desktop Name or the binary, and neither "
        "is reliably what a person says (D33)"
    )


# --- criterion 3.7: the list is DERIVED, and is a superset of the last one ---


#: The hand-written `STT_HOTWORDS` exactly as it stood at commit cb5836f, the
#: last one before the derivation. The criterion is "superset of today's", so
#: this is what "today's" was. It is a frozen historical value: do NOT edit it
#: to make a change pass — a word disappearing from the bias is the D26/D31
#: defect, and this list is the only thing that would notice.
_HAND_WRITTEN = (
    "Brave, foot, terminal, Visual Studio Code, VLC, mpv, Neovim, Arch Linux, "
    "Kathmandu, lo-fi, jazz, YouTube, dark theme, web search, "
    "Wi-Fi, wifi, volume, mute, unmute, brightness, workspace, fullscreen, "
    "clipboard, dictation, notes, timer, reminder, quiet mode, media, "
    "pause, resume, next track, previous track, "
    "Firefox, Zen Browser, LibreWolf, Discord, Spotify, Obsidian, Anytype, "
    "Claude, Thunar, Kitty, PyCharm, WebStorm, IntelliJ IDEA, Android Studio, "
    "Zed, Todoist, Thunderbird, btop, Heroic, Timeshift"
)


def test_the_derived_list_is_a_superset_of_the_hand_written_one():
    from friday.capabilities import stt_hotwords

    before = {w.strip() for w in _HAND_WRITTEN.split(",") if w.strip()}
    after = {w.strip() for w in stt_hotwords().split(",") if w.strip()}
    assert before <= after, f"the derivation DROPPED: {sorted(before - after)}"


def test_every_hotword_belongs_to_a_capability():
    """The other direction, and the reason the list can be trusted now: a word
    that biases Whisper toward nothing Friday can do is noise in the decoder,
    and there is no second list where one could hide."""
    from friday.capabilities import CAPABILITIES, stt_hotwords

    owned = {w for c in CAPABILITIES.values() for w in c.hotwords}
    assert {w.strip() for w in stt_hotwords().split(",")} == owned


def test_config_uses_the_derived_list_unless_the_environment_overrides_it():
    from friday.capabilities import stt_hotwords

    assert config.STT_HOTWORDS == stt_hotwords()
