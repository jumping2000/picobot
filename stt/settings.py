"""Impostazioni del servizio di trascrizione, lette dall'ambiente (variabili STT_*)."""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SttSettings:
    model: str = "small"            # modello faster-whisper multilingua
    compute_type: str = "int8"      # quantizzazione per CPU
    threads: int = 4                # core del N100
    beam_size: int = 1              # 1 piu' veloce, 5 piu' accurato
    languages: list[str] = field(default_factory=lambda: ["it", "en"])   # lingue ammesse
    max_mb: int = 20
    max_seconds: int = 300

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "SttSettings":
        langs = [x.strip().lower() for x in env.get("STT_LANGUAGES", "it,en").split(",") if x.strip()]
        return cls(
            model=env.get("STT_MODEL", "small"),
            compute_type=env.get("STT_COMPUTE_TYPE", "int8"),
            threads=int(env.get("STT_THREADS", "4")),
            beam_size=int(env.get("STT_BEAM_SIZE", "1")),
            languages=langs or ["it", "en"],
            max_mb=int(env.get("STT_MAX_MB", "20")),
            max_seconds=int(env.get("STT_MAX_SECONDS", "300")),
        )
