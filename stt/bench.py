"""Misura dei modelli sul tuo hardware (es. N100), per scegliere STT_MODEL e STT_BEAM_SIZE.

Uso (nel container, con i file audio copiati in ./models sull'host):
    docker compose --profile stt run --rm stt python bench.py /models/vocale_it.ogg /models/vocale_en.ogg
    python bench.py FILE [FILE...] --models base small --beams 1 5

RTF = secondi impiegati / durata dell'audio: sotto 1 la trascrizione e' piu' veloce del parlato.
"""
import argparse
import dataclasses
import time

from settings import SttSettings
from transcriber import FasterWhisperTranscriber, choose_language


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--models", nargs="+", default=["base", "small"])
    p.add_argument("--beams", nargs="+", type=int, default=[1, 5])
    args = p.parse_args()
    base = SttSettings.from_env()

    print(f"{'modello':<8} {'beam':>4} {'audio s':>8} {'tempo s':>8} {'RTF':>5}  lingua  testo")
    for model in args.models:
        for beam in args.beams:
            t = FasterWhisperTranscriber(dataclasses.replace(base, model=model, beam_size=beam))
            t.load()                                  # escluso dalla misura: avviene una volta sola
            for path in args.files:
                start = time.perf_counter()
                clip = t.decode(path)
                lang = choose_language(t.language_probs(clip), base.languages)
                text = t.transcribe(clip, lang)
                elapsed = time.perf_counter() - start
                rtf = elapsed / clip.duration if clip.duration else 0.0
                print(f"{model:<8} {beam:>4} {clip.duration:>8.1f} {elapsed:>8.1f} {rtf:>5.2f}  {lang:<6}  {text[:80]}")


if __name__ == "__main__":
    main()
