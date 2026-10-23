from settings import SttSettings
from transcriber import choose_language


def test_choose_language_picks_best_allowed():
    assert choose_language([("es", 0.6), ("it", 0.3), ("en", 0.1)], ["it", "en"]) == "it"
    assert choose_language([("en", 0.7), ("it", 0.2)], ["it", "en"]) == "en"


def test_choose_language_falls_back_to_first_allowed():
    assert choose_language([("es", 0.9)], ["it", "en"]) == "it"
    assert choose_language([], ["it", "en"]) == "it"


def test_settings_from_env_defaults_and_override():
    d = SttSettings.from_env({})
    assert (d.model, d.compute_type, d.threads, d.beam_size) == ("small", "int8", 4, 1)
    assert d.languages == ["it", "en"] and (d.max_mb, d.max_seconds) == (20, 300)
    o = SttSettings.from_env({"STT_MODEL": "base", "STT_LANGUAGES": " IT , en ", "STT_BEAM_SIZE": "5"})
    assert (o.model, o.languages, o.beam_size) == ("base", ["it", "en"], 5)
