from friday.audio.dictation import DictationManager, format_dictation, is_start_dictation, is_stop_dictation


def test_dictation_phrase_detection():
    assert is_start_dictation("start dictation")
    assert is_start_dictation("begin dictation mode")
    assert not is_start_dictation("start firefox")

    assert is_stop_dictation("stop dictation")
    assert is_stop_dictation("end dictation")
    assert not is_stop_dictation("stop music")


def test_format_dictation_punctuation():
    text = "hello world period how are you question mark new line fine comma thanks exclamation mark"
    formatted = format_dictation(text)
    assert formatted == "hello world. how are you?\nfine, thanks!"


def test_dictation_manager_toggle(monkeypatch):
    dm = DictationManager()
    assert not dm.is_dictating

    typed = []
    monkeypatch.setattr("friday.audio.dictation.type_text", lambda s: typed.append(s) or True)

    dm.start()
    assert dm.is_dictating

    # When dictating, transcript is typed verbatim
    dm.handle_transcript("open brave and search")
    assert typed == ["open brave and search "]

    dm.stop()
    assert not dm.is_dictating
