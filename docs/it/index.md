# Documentazione di PicoBot

🇮🇹 Italiano · 🇬🇧 [English](../en/index.md) · ⬅️ [README](../../README_IT.md)

PicoBot v0.5 è un assistente personale multi-agente self-hosted, basato su [Agno 3](https://github.com/agno-agi/agno).
Si usa da Telegram, da una CLI interattiva e da un'API REST, tutti serviti da un unico processo.

## Guide

| Pagina | Contenuto |
|---|---|
| [Per iniziare](getting-started.md) | Requisiti, installazione con Docker e in locale, primo avvio |
| [Configurazione](configuration.md) | Tutte le variabili d'ambiente, con il valore predefinito |
| [Architettura](architecture.md) | Router, team, workflow, scheduler, dati, ciclo di una richiesta |
| [Canali](channels.md) | Telegram e CLI: comandi, documenti, conferme |
| [API REST](api.md) | Endpoint, payload, esempi, codici di errore |
| [Skill](skills.md) | Formato Agent Skills, CLI di amministrazione, dipendenze Docker |
| [MCP](mcp.md) | Collegare server Model Context Protocol |
| [Messaggi vocali](voice.md) | Note vocali e audio Telegram, il container di trascrizione `stt` |
| [Memoria](memory.md) | Memorie, profilo strutturato, entità, `/memory` e `/forget` |
| [Scheduler](scheduler.md) | Task ricorrenti con cron e relativi limiti |
| [Sicurezza](security.md) | Modello di minaccia, sandbox, autenticazione, limiti noti |
| [Sviluppo](development.md) | Struttura del progetto, test, punti di estensione |
| [Risoluzione problemi](troubleshooting.md) | Errori frequenti e come risolverli |

## Glossario

| Termine | Significato |
|---|---|
| **Router** | Il team Agno di primo livello (`PicoBot`). Risponde da solo o delega; è l'unico agente che scrive memorie, profilo ed entità |
| **SimpleTeam** | Team sul modello economico: Web, Finance, Coder |
| **ComplexTeam** | Team sul modello forte: Researcher, Analyst, Writer, Critic (opzionale), con skill e MCP |
| **DocSummary** | Workflow Agno che riassume un documento caricato |
| **Skill** | Cartella in formato Agent Skills (`SKILL.md` + eventuali script e riferimenti) |
| **Workspace** | `workspace/`: l'unica cartella in cui gira il codice generato; i file consegnati escono da `workspace/outputs/` |
| **Outbox** | `data/outbox/`: copie per utente dei file consegnati, scaricabili dall'API per 24 ore |
| **HITL** | Human-in-the-loop: ogni esecuzione di codice richiede un'approvazione esplicita |

## Altri documenti

- [Collaudo manuale](../manual-qa.md)
- Spec di design e piani di implementazione: [`docs/superpowers/`](../superpowers/)
