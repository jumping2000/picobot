"""Facciata async verso router, workflow documenti e scheduler: i canali non toccano Agno."""
import asyncio
import dataclasses
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import time
from pathlib import Path
from urllib.parse import urlsplit

from agno.models.message import Message
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput
from agno.session import TeamSession
from agno.team import Team
from agno.workflow import Workflow

from . import skills_cli, web
from .config import Settings
from .context import Reply, RunCtx, reset_ctx, set_ctx
from .documents import DocumentError
from .mcp_loader import close_mcp_tools, load_mcp_tools
from .scheduler import Scheduler
from .prompts import router_instructions
from .skills import SkillInfo, SkillRegistry
from .team import build_router
from .tools.files import purge_outbox
from .trace import build_trace, summary_line, write_trace
from .web import fetch_article
from .workflows.doc_summary import build_doc_workflow, run_summary, run_summary_text

logger = logging.getLogger(__name__)


TARGETS = {"auto": None, "simple": "SimpleTeam", "complex": "ComplexTeam"}
_PROFILE_META = {"user_id", "agent_id", "team_id", "created_at", "updated_at"}


@dataclass
class MemoryReport:
    memories: list[str]
    profile: dict[str, str]                    # solo i campi valorizzati
    entities: list[tuple[str, str, str]]       # (nome, tipo, descrizione)


class PicoBotService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.team: Team | None = None
        self.doc_flow: Workflow | None = None
        self.scheduler: Scheduler | None = None
        self._mcp: list = []
        self.registry = SkillRegistry(settings)   # skill globali, ricaricate a caldo

    async def start(self) -> None:
        self.s.workspace_dir.mkdir(parents=True, exist_ok=True)
        try:
            purge_outbox(self.s)
        except OSError:
            logger.exception("Pulizia outbox fallita")
        self._mcp = await load_mcp_tools(self.s.mcp_config_path)
        self.doc_flow = build_doc_workflow(self.s)
        self.scheduler = Scheduler(self.s, self._ask_text)   # prima del router: i suoi tool lo usano
        self.team = build_router(self.s, self.registry, mcp_tools=self._mcp, doc_flow=self.doc_flow,
                                 scheduler=self.scheduler)
        self.team.initialize_team()   # necessario per leggere/scrivere sessioni fuori da un run (riassunti)
        logger.info("PicoBot pronto (modello=%s, strong=%s, mcp=%d).",
                    self.s.llm_model_id, self.s.strong_model_id, len(self._mcp))

    async def stop(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        await close_mcp_tools(self._mcp)

    async def ask(self, text: str, *, user_id: str, session_id: str, ctx: RunCtx | None = None,
                  target: str = "auto") -> Reply:
        """Risposta testuale + file consegnati dagli agenti (deliver_file) durante la richiesta.

        target: "auto" (decide il router), "simple" o "complex" (team richiamato direttamente, senza router).
        """
        assert self.team is not None, "start() non chiamato"
        if target not in TARGETS:
            raise ValueError(f"target non valido: {target!r} (ammessi: {', '.join(sorted(TARGETS))})")
        if self.registry.refresh():   # skill aggiunte/rimosse sull'host: le vedono subito router e ComplexTeam
            self.team.instructions = router_instructions(self.registry.names(), self.s.skills_router_hint_max)
        ctx = ctx or RunCtx(user_id=user_id, channel="unknown")
        runner = self.team if target == "auto" else self._member(TARGETS[target])
        # un team richiamato direttamente non usa MAI l'id di sessione del router (non deve sovrascriverla)
        run_sid = session_id if target == "auto" else f"{session_id}:{target}"
        token = set_ctx(ctx)
        t0, out, err = time.monotonic(), None, None
        try:
            out = await runner.arun(text, user_id=user_id, session_id=run_sid)
        except Exception as e:
            err = e
            raise
        finally:
            reset_ctx(token)
            self._trace(out, text, ctx, session_id, target, time.monotonic() - t0, err)
        content = out.content if isinstance(out.content, str) else str(out.content)
        if target != "auto":   # lo scambio entra nella sessione del router: i follow-up hanno il contesto
            await self._record_in_session(session_id, user_id, f"[/{target}] {text}", content)
        return Reply(content, list(ctx.outputs))

    def _trace(self, out, text: str, ctx: RunCtx, session_id: str, target: str, duration_s: float,
               error: BaseException | None) -> None:
        """Percorso della richiesta in data/trace.jsonl (TRACE_ENABLED). Non fa mai fallire la richiesta."""
        if not self.s.trace_enabled:
            return
        try:
            rec = build_trace(out, text=text, ctx=ctx, session_id=session_id, target=target,
                              duration_s=duration_s, error=error)
            write_trace(self.s, rec)
            logger.info(summary_line(rec))
        except Exception:  # noqa: BLE001
            logger.exception("Traccia della richiesta non scritta")

    def _member(self, name: str):
        return next(m for m in self.team.members if m.name == name)

    def skill_info(self) -> list[SkillInfo]:
        self.registry.refresh()
        return self.registry.info()

    @asynccontextmanager
    async def fetched_skill(self, source: str, *, allow_local: bool) -> AsyncIterator[Path]:
        """Sorgente di una skill da chat -> percorso locale (cartella o .zip). La cartella temporanea sparisce sempre.

        Solo https:// (zip scaricato o repository git); percorsi locali solo con allow_local (chat CLI).
        """
        source = source.strip()
        low = source.lower()
        if "://" in source or low.startswith("git@"):
            if not low.startswith("https://"):
                raise skills_cli.SkillInstallError("Solo link https://")
        elif not allow_local:
            raise skills_cli.SkillInstallError(
                "Da Telegram manda un link https:// o allega uno .zip con didascalia /skill_add")
        else:
            yield Path(source).expanduser()
            return
        tmp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="picobot-skill-"))
        try:
            try:
                if urlsplit(source).path.lower().endswith(".zip"):
                    data = await web.fetch_bytes(source, max_bytes=skills_cli.MAX_SKILL_BYTES)
                    path = tmp / "skill.zip"
                    await asyncio.to_thread(path.write_bytes, data)
                else:
                    await web.check_public_url(source)   # host pubblico prima di qualsiasi richiesta di git
                    url = "https://" + source[len("https://"):]   # _fetch riconosce solo lo schema minuscolo
                    path = await asyncio.to_thread(skills_cli._fetch, url, tmp, strict_git=True)
            except DocumentError as e:
                raise skills_cli.SkillInstallError(str(e)) from e
            yield path
        finally:
            await asyncio.to_thread(shutil.rmtree, tmp, ignore_errors=True)

    async def install_skill(self, path: Path, *, force: bool) -> SkillInfo:
        return await asyncio.to_thread(skills_cli.install, str(path), self.s.skills_dir, force)

    async def remove_skill(self, name: str) -> None:
        await asyncio.to_thread(skills_cli.remove, name, self.s.skills_dir)

    async def _ask_text(self, text: str, *, user_id: str, session_id: str, ctx: RunCtx | None = None) -> str:
        """Solo testo: usata dallo scheduler (gli schedule non producono file)."""
        return (await self.ask(text, user_id=user_id, session_id=session_id, ctx=ctx)).text

    async def summarize(self, path: Path, instruction: str = "", *, user_id: str, name: str = "",
                        session_id: str | None = None) -> str:
        assert self.doc_flow is not None
        # estrazione PRIMA del workflow: gli errori (DocumentError) arrivano al canale invece di essere inghiottiti
        summary = await run_summary(self.doc_flow, self.s, path, instruction, user_id=user_id, name=name)
        if session_id:   # il riassunto entra nella storia della sessione: follow-up possibili
            await self._record_in_session(session_id, user_id,
                                          f"[Documento caricato: {name or path.name}] {instruction.strip()}".strip(), summary)
        return summary

    async def summarize_url(self, url: str, instruction: str = "", *, user_id: str,
                            session_id: str | None = None) -> str:
        assert self.doc_flow is not None
        text = await fetch_article(url)   # come per i documenti: i DocumentError arrivano al canale
        summary = await run_summary_text(self.doc_flow, text[: self.s.doc_max_chars], len(text) > self.s.doc_max_chars,
                                         instruction, user_id=user_id, name=url)
        if session_id:
            await self._record_in_session(session_id, user_id, f"[Pagina web: {url}] {instruction.strip()}".strip(), summary)
        return summary

    async def _record_in_session(self, session_id: str, user_id: str, user_text: str, answer: str) -> None:
        """Aggiunge uno scambio user/assistant alla sessione del router SENZA chiamate LLM."""
        team = self.team
        try:
            session = await team.aget_session(session_id=session_id, user_id=user_id)
            if session is None:
                session = TeamSession(session_id=session_id, team_id=team.id, user_id=user_id,
                                      runs=[], created_at=int(time.time()))
            run = TeamRunOutput(
                run_id=f"doc-{time.time_ns()}", team_id=team.id, session_id=session_id, user_id=user_id,
                content=answer, status=RunStatus.completed, created_at=int(time.time()),
                messages=[Message(role="user", content=user_text), Message(role="assistant", content=answer)],
            )
            session.upsert_run(run)
            await team.asave_session(session)               # record di sessione
            team.db.upsert_run(run, session_id=session_id, user_id=user_id)  # i run stanno in tabella separata
        except Exception:  # noqa: BLE001  il riassunto resta valido anche se la sessione non si aggiorna
            logger.exception("Impossibile registrare il riassunto nella sessione %s", session_id)

    async def memories(self, user_id: str) -> list[str]:
        assert self.team is not None
        return [m.memory for m in (await self.team.aget_user_memories(user_id=user_id) or [])]

    async def memory_report(self, user_id: str) -> MemoryReport:
        """Memorie, profilo ed entita' dell'utente (per /memory e GET /v1/memory)."""
        assert self.team is not None
        memories = await self.memories(user_id) if self.team.memory_manager is not None else []
        profile, entities = {}, []
        lm = self.team.learning if self.s.enable_learning else None
        if lm is not None:
            p = await lm.user_profile_store.aget(user_id=user_id)
            if p is not None:
                profile = {f.name: str(v) for f in dataclasses.fields(p)
                           if f.name not in _PROFILE_META and (v := getattr(p, f.name, None))}
            ents = await lm.entity_memory_store.alist_entities(user_id=user_id, namespace="user", limit=50)
            entities = [(e.name, e.entity_type or "", e.description or "") for e in ents or []]
        return MemoryReport(memories, profile, entities)

    async def forget(self, user_id: str) -> None:
        """Cancella memorie, profilo ed entita' dell'utente. Solleva se una parte non viene cancellata."""
        assert self.team is not None
        if self.s.enable_learning and self.team.db is not None:
            self.team.db.delete_user_learnings(user_id)          # profilo + entita' (namespace privato)
        if self.team.memory_manager is not None:
            await self.team.memory_manager.aclear_user_memories(user_id=user_id)
