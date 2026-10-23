"""Workflow Agno: riassunto documento = estrai (codice) -> [map in parallelo se lungo] -> riduci (1 agente)."""
import asyncio
from pathlib import Path

from agno.agent import Agent
from agno.workflow import Step, StepInput, StepOutput, Workflow

from .. import prompts
from ..config import Settings
from ..documents import extract_text, split_chunks
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


async def run_summary(flow: Workflow, s: Settings, path: Path, instruction: str, *, user_id: str, name: str) -> str:
    """Estrae il testo (gli errori escono come DocumentError) ed esegue il workflow."""
    text, truncated = await asyncio.to_thread(extract_text, path, s.doc_max_chars)
    out = await flow.arun(
        input="riassunto",
        additional_data={"text": text, "truncated": truncated, "name": name or path.name,
                         "instruction": instruction.strip()[:1000]},
        user_id=user_id,
    )
    return out.content if isinstance(out.content, str) else str(out.content)
