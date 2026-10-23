"""Workflow Agno: riassunto documento = estrai (codice) -> [map in parallelo se lungo] -> riduci (1 agente)."""
import asyncio

from agno.agent import Agent
from agno.workflow import Step, StepInput, StepOutput, Workflow

from .. import prompts
from ..config import Settings
from ..documents import split_chunks
from ..models import make_model


def build_doc_workflow(s: Settings) -> Workflow:
    mapper = Agent(name="ChunkSummarizer", model=make_model(s), instructions=[prompts.DOC_MAP])
    reducer = Agent(name="Summarizer", model=make_model(s), instructions=[prompts.DOC_REDUCE], markdown=True)
    sem = asyncio.Semaphore(4)

    async def prepare(step_input: StepInput) -> StepOutput:
        data = step_input.additional_data or {}
        text, truncated = data["text"], data["truncated"]   # estratto prima (errori -> DocumentError)
        chunks = split_chunks(text, s.doc_chunk_chars)
        if len(chunks) > 1:  # map: riassunti parziali concorrenti (modello economico)
            async def one(i: int, c: str) -> str:
                async with sem:
                    r = await mapper.arun(f"Frammento {i + 1}/{len(chunks)}:\n{c}")
                    return f"[Parte {i + 1}] {r.content}"
            text = "\n\n".join(await asyncio.gather(*(one(i, c) for i, c in enumerate(chunks))))
        note = "\n(Nota: documento troncato al limite massimo.)" if truncated else ""
        request = data.get("instruction") or "Riassumi il documento."
        return StepOutput(content=(f"Richiesta dell'utente: {request}\n\n"
                                   f"<documento nome=\"{data.get('name', '')}\">\n{text}\n</documento>{note}"))

    return Workflow(
        name="DocSummary",
        steps=[Step(name="prepare", executor=prepare), Step(name="summarize", agent=reducer)],
    )
