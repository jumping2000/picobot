# Skill

🇮🇹 Italiano · 🇬🇧 [English](../en/skills.md) · ⬅️ [Indice](index.md)

Le skill sono pacchetti di istruzioni che insegnano al **ComplexTeam** un compito specifico (per esempio creare file
Word, PowerPoint o Excel). Sono globali: tutti gli utenti vedono le stesse skill.

## Formato

Una skill è una cartella in formato [Agent Skills](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills):

```
skills/
└── docx/
    ├── SKILL.md          # obbligatorio, con frontmatter YAML
    ├── scripts/          # opzionale: script di riferimento (mai eseguiti direttamente)
    ├── requirements.txt  # opzionale: dipendenze Python
    ├── package.json      # opzionale: dipendenze Node ("dependencies")
    └── apt.txt           # opzionale: pacchetti Debian
```

```markdown
---
name: docx
description: Crea e modifica documenti Word con revisioni, commenti e formattazione.
---
# Istruzioni
...
```

Regole di validazione:

- il nome della cartella deve essere uguale a `name` e rispettare `^[a-z0-9-]{1,64}$`;
- `description` non deve essere vuota;
- le cartelle che iniziano con `.` o `_` sono ignorate;
- la CLI di amministrazione rifiuta anche symlink e skill oltre 50 MB.

Le cartelle non valide vengono saltate e registrate nel log (`Skill '<nome>' ignorata: <motivo>`).

## Installare e rimuovere

**A mano:** copia la cartella in `./skills/` (montata in sola lettura su `/app/skills`); cancellala per
disinstallare. Il bot vede la modifica alla **richiesta successiva, senza riavvio**.

**CLI di amministrazione** (sull'host; fa tutti i controlli e installa in modo atomico):

```bash
uv run picobot skills add /percorso/docx              # cartella
uv run picobot skills add skill.zip                   # zip (path traversal e symlink rifiutati)
uv run picobot skills add https://github.com/org/repo.git   # repository git (serve git)
uv run picobot skills add skill.zip --force           # sostituisce una skill gia' installata
uv run picobot skills list
uv run picobot skills remove docx
uv run picobot skills validate                        # cartelle che il bot ignorerebbe (exit 1 se ce ne sono)
uv run picobot skills --dir /altra/cartella list      # cartella diversa
```

Cartella di default: `SKILLS_DIR` se esiste, altrimenti `./skills`. La sorgente può avere `SKILL.md` alla radice o
in un'unica sottocartella.

> [!NOTE]
> Le skill non si installano da chat né da API. Su Telegram e nella CLI `/skills` si limita a elencarle.

## Come le usano gli agenti

1. Il router conosce solo i **nomi** delle skill (fino a `SKILLS_ROUTER_HINT_MAX` = 15) per decidere quando
   delegare al ComplexTeam (circa 6 token per nome a ogni chiamata).
2. I membri del ComplexTeam ricevono uno snippet di lunghezza fissa e chiamano `list_skills(compito)`, che ordina le
   skill per pertinenza (circa 40 token per skill, una volta per task, max `SKILLS_LIST_MAX`).
3. Leggono quella pertinente con `get_skill_instructions(nome)` e i suoi riferimenti.
4. Gli script dentro le skill **non vengono mai eseguiti direttamente** (`get_skill_script` è disattivato):
   l'Analyst o il Writer scrivono il codice e lo lanciano con `run_python` / `run_node`, e ogni esecuzione chiede
   la tua conferma.

## Dipendenze (punti di estensione)

Le librerie richieste dalle skill vengono installate nell'immagine Docker tramite quattro file:

| File | Contenuto | Installato con |
|---|---|---|
| `deps/apt.txt` | Pacchetti Debian (`pacchetto` o `pacchetto=versione`) | `apt-get install` |
| `deps/pip.txt` | Librerie Python, versione esatta (`openpyxl==3.1.5`) | `uv pip install` nel venv del bot |
| `deps/npm.txt` | Pacchetti Node globali, versione esatta (`docx@9.9.0`) | `npm install -g` (trovati via `NODE_PATH`) |
| `deps/setup.sh` | Hook libero, eseguito come root durante la build | `bash` |

Una dipendenza per riga, con un commento `# skill: <nome>` che indica la skill che la richiede. Già presenti quelle
delle skill di esempio: `docx@9.9.0`, `pptxgenjs@4.0.1`, `openpyxl==3.1.5`.

```bash
uv run picobot skills deps            # dichiarate dalle skill (requirements.txt, package.json, apt.txt) ma assenti da deps/
uv run picobot skills deps --write    # le aggiunge a deps/*.txt (non installa nulla)
docker compose build && docker compose up -d
```

Il confronto avviene per nome del pacchetto, non per versione.

## Skill Office di esempio

> [!CAUTION]
> Le skill di esempio `docx`, `pptx` e `xlsx` hanno licenza "All rights reserved" (termini Anthropic): solo uso
> personale, non ridistribuirle. `skills/` è in `.gitignore`.

Senza LibreOffice nell'immagine, il bot **crea** i file ma salta validazione, ricalcolo delle formule (si calcolano
all'apertura in Excel), anteprime e conversioni PDF. Aggiungere `libreoffice` a `deps/apt.txt` e ricostruire
dovrebbe abilitarle; questa configurazione non è coperta dai test e rende l'immagine molto più grande.
