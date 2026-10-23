"""Facciata async verso router, workflow documenti e scheduler: i canali non toccano Agno."""
import asyncio
import logging
import time
from pathlib import Path

from agno.models.message import Message
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput
from agno.session import TeamSession
from agno.team import Team
from agno.workflow import Workflow

from .config import Settings
from .context import RunCtx, reset_ctx, set_ctx
from .documents import extract_text
from .mcp_loader import close_mcp_tools, load_mcp_tools
from .scheduler import Scheduler
from .team import build_router
from .workflows.doc_summary import build_doc_workflow

logger = logging.getLogger(__name__)


class PicoBotService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.team: Team | None = None
        self.doc_flow: Workflow | None = None
        self.scheduler: Scheduler | None = None
        self._mcp: list = []

    async def start(self) -> None:
        self.s.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._mcp = await load_mcp_tools(self.s.mcp_config_path)
        self.team = build_router(self.s, extra_tools=self._mcp)
        self.team.initialize_team()   # necessario per leggere/scrivere sessioni fuori da un run (riassunti)
        self.doc_flow = build_doc_workflow(self.s)
        self.scheduler = Scheduler(self.s, self.ask)
        logger.info("PicoBot pronto (modello=%s, strong=%s, mcp=%d).",
                    self.s.llm_model_id, self.s.strong_model_id, len(self._mcp))

    async def stop(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        await close_mcp_tools(self._mcp)

    async def ask(self, text: str, *, user_id: str, session_id: str, ctx: RunCtx | None = None) -> str:
        assert self.team is not None, "start() non chiamato"
        token = set_ctx(ctx or RunCtx(user_id=user_id, channel="unknown"))
        try:
            out = await self.team.arun(text, user_id=user_id, session_id=session_id)
        finally:
            reset_ctx(token)
        return out.content if isinstance(out.content, str) else str(out.content)

    async def summarize(self, path: Path, instruction: str = "", *, user_id: str, name: str = "",
                        session_id: str | None = None) -> str:
        assert self.doc_flow is not None
        # estrazione PRIMA del workflow: gli errori (DocumentError) arrivano al canale invece di essere inghiottiti
        text, truncated = await asyncio.to_thread(extract_text, path, self.s.doc_max_chars)
        out = await self.doc_flow.arun(
            input="riassunto",
            additional_data={"text": text, "truncated": truncated, "name": name or path.name,
                             "instruction": instruction.strip()[:1000]},
            user_id=user_id,
        )
        content = out.content
        summary = content if isinstance(content, str) else str(content)
        if session_id:   # il riassunto entra nella storia della sessione: follow-up possibili
            await self._record_in_session(session_id, user_id,
                                          f"[Documento caricato: {name or path.name}] {instruction.strip()}".strip(), summary)
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

    async def forget(self, user_id: str) -> None:
        assert self.team is not None and self.team.memory_manager is not None
        await self.team.memory_manager.aclear_user_memories(user_id=user_id)
