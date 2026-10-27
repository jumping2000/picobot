import os

__version__ = "0.7.1"

# Privacy: Agno invia telemetria a os-api.agno.com di default. Un assistente privato non deve farlo,
# salvo scelta esplicita (AGNO_TELEMETRY=true nell'ambiente). Va impostato prima di creare agenti e team.
os.environ.setdefault("AGNO_TELEMETRY", "false")
