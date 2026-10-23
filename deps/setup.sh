#!/usr/bin/env bash
# Hook opzionale, eseguito come root durante la build come ultimo passo delle dipendenze:
# per tutto cio' che non sta in apt.txt / pip.txt / npm.txt (font, binari scaricati, configurazioni).
set -euo pipefail
# esempio:
# fc-cache -f
