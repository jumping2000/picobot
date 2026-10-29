# Skills

🇬🇧 English · 🇮🇹 [Italiano](../it/skills.md) · ⬅️ [Index](index.md)

Skills are instruction packages that teach the **ComplexTeam** a specific task (e.g. creating Word, PowerPoint or
Excel files). They are global: every user sees the same skills.

## Format

A skill is a folder in [Agent Skills](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills) format:

```
skills/
└── docx/
    ├── SKILL.md          # required, with YAML frontmatter
    ├── scripts/          # optional: reference scripts (never executed directly)
    ├── requirements.txt  # optional: Python dependencies
    ├── package.json      # optional: Node dependencies ("dependencies")
    └── apt.txt           # optional: Debian packages
```

```markdown
---
name: docx
description: Create and edit Word documents with tracked changes, comments and formatting.
---
# Instructions
...
```

Validation rules:

- the folder name must equal `name` and match `^[a-z0-9-]{1,64}$`;
- `description` must be non-empty;
- folders starting with `.` or `_` are ignored;
- the admin CLI (and the chat commands) also reject symlinks and skills larger than 50 MB.

Invalid folders are skipped and logged (`Skill '<name>' ignorata: <reason>`).

## Installing and removing

**Manual:** copy the folder into `./skills/` (mounted at `/app/skills`); delete it to uninstall.
The bot picks up the change at the **next request, without restart**.

**Admin CLI** (on the host; checks everything and installs atomically):

```bash
uv run picobot skills add /path/to/docx              # folder
uv run picobot skills add skill.zip                  # zip (path traversal and symlinks are rejected)
uv run picobot skills add https://github.com/org/repo.git   # git repository (git required)
uv run picobot skills add skill.zip --force          # replace an installed skill
uv run picobot skills list
uv run picobot skills remove docx
uv run picobot skills validate                       # folders the bot would ignore (exit 1 if any)
uv run picobot skills --dir /other/skills list       # different folder
```

Default folder: `SKILLS_DIR` if it exists, otherwise `./skills`. The source may contain `SKILL.md` at its root or in
a single subfolder.

> [!NOTE]
> Skills cannot be installed from the API. For Telegram and the CLI chat see the next section.

## From Telegram and the CLI chat

| Channel | Command | Source |
|---|---|---|
| Telegram | `/skill_add <url>` | `https://` URL ending in `.zip` (before `?` and `#`, case-insensitive): downloaded zip. Any other `https://` URL: git repository |
| Telegram | `.zip` attachment with caption `/skill_add` | the attached zip (at most `MAX_UPLOAD_MB`) |
| CLI chat | `/skill_add <path or url>` | local path (folder or `.zip`), or a URL as above |
| Both | `/skill_remove <name>` | — |

- **Admins only.** On Telegram your id must be in `ADMIN_USER_IDS` (in `.env`, see
  [Configuration](configuration.md)); with the key empty the commands are off, and `ALLOW_ALL_USERS=true` makes
  nobody an admin. Other users are refused. In the CLI chat the commands are always allowed: whoever opens the CLI
  already has a shell in the container.
- **Local paths only from the CLI.** Telegram accepts only URLs or attachments, and only `https://`.
- **Result.** The bot replies with the skill's name and description, the declared dependencies
  (`requirements.txt`, `package.json`, `apt.txt`) and a warning if it contains `scripts/`. The skill is active from
  the next request.
- **Skill already present.** The bot asks whether to replace it: Yes/No buttons on Telegram, `[y/N]` in the CLI. No
  answer within `CONFIRM_TIMEOUT_S` replaces nothing.
- **Dependencies.** From chat the bot **reports** them but does not install them: on the host run
  `uv run picobot skills deps --write` and rebuild the image (see
  [Dependencies](#dependencies-extension-points)).
- **Log.** Every install and removal, successful or failed, is logged at INFO level with user, channel, source
  (credentials and query stripped) and outcome.

Limits:

- no links to a subfolder of a repository (`github.com/<org>/<repo>/tree/<branch>/<path>`) and no repositories with
  several skills: `SKILL.md` must be at the root or in a single subfolder;
- no private repositories or git credentials (the clone never asks for a username or password);
- from chat, git does not follow HTTP redirects: a URL that answers with a redirect (for example `www.github.com`
  instead of `github.com`) fails and the bot asks for the current URL. A renamed or transferred GitHub repository
  still clones fine;
- downloaded zip at most 50 MB, with an overall 120 s timeout; `git clone` with a 120 s timeout;
- hosts on local or private networks are rejected (see [Security](security.md#skill-installation)).

If the bot says it cannot write to the skills folder, run on the host: `sudo chown -R 1000 skills`.

> [!IMPORTANT]
> **When upgrading from an earlier version**, `./skills` used to be mounted read-only. The compose file now mounts it
> read-write, and the container user (UID 1000) must be able to write to it: `sudo chown -R 1000 skills`.
> If your host user has UID 1000 (the first user of a typical Linux install), copying folders into `./skills` and
> using `picobot skills add` keep working as before; with another UID you need `sudo`, or the chat commands. Docker
> Desktop on Mac and Windows is not affected.

## How agents use them

1. The router knows only the skill **names** (up to `SKILLS_ROUTER_HINT_MAX` = 15) to decide when to delegate to the
   ComplexTeam (~6 tokens per name per call).
2. ComplexTeam members receive a fixed-length snippet and call `list_skills(task)`, which ranks skills by relevance
   (~40 tokens per skill, once per task, max `SKILLS_LIST_MAX`).
3. They read the relevant skill with `get_skill_instructions(name)` and its references.
4. Scripts inside skills are **never executed directly** (`get_skill_script` is disabled): the Analyst or the
   Writer writes code and runs it with `run_python` / `run_node`, and every run asks for your confirmation.

## Dependencies (extension points)

Libraries needed by skills are installed in the Docker image through four files:

| File | Contents | Installed with |
|---|---|---|
| `deps/apt.txt` | Debian packages (`package` or `package=version`) | `apt-get install` |
| `deps/pip.txt` | Python libraries, exact version (`openpyxl==3.1.5`) | `uv pip install` in the bot venv |
| `deps/npm.txt` | Global Node packages, exact version (`docx@9.9.0`) | `npm install -g` (found via `NODE_PATH`) |
| `deps/setup.sh` | Free-form hook, run as root at build time | `bash` |

One dependency per line, with a `# skill: <name>` comment naming the skill that needs it. Already present for the
sample skills: `docx@9.9.0`, `pptxgenjs@4.0.1`, `openpyxl==3.1.5`.

```bash
uv run picobot skills deps            # declared by skills (requirements.txt, package.json, apt.txt) but missing from deps/
uv run picobot skills deps --write    # append them to deps/*.txt (installs nothing)
docker compose build && docker compose up -d
```

Comparison is by package name, not version.

## Sample Office skills

> [!CAUTION]
> The sample `docx`, `pptx` and `xlsx` skills are licensed "All rights reserved" (Anthropic terms): personal use
> only, do not redistribute them. `skills/` is in `.gitignore`.

Without LibreOffice in the image, the bot **creates** the files but skips validation, formula recalculation
(formulas are computed when the file is opened in Excel), previews and PDF conversion. Adding `libreoffice` to
`deps/apt.txt` and rebuilding should enable them; this setup is not covered by the tests and makes the image much
larger.
