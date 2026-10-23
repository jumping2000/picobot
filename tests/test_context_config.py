from picobot.config import Settings
from picobot.context import Reply, RunCtx


def test_defaults():
    s = Settings()
    assert (s.code_node_mem_mb, s.code_max_runs, s.max_output_mb, s.max_output_files, s.outbox_ttl_h) == (1536, 6, 20, 5, 24)
    assert s.output_ext_set == {"docx", "pptx", "xlsx", "csv", "txt", "md", "pdf", "html", "json", "py"}
    assert (s.skills_list_max, s.skills_router_hint_max, s.enable_skills) == (50, 15, True)
    assert s.outputs_dir == s.workspace_dir / "outputs" and s.outbox_dir == s.data_dir / "outbox"


def test_runctx_and_reply():
    c = RunCtx("u", "api")
    assert c.outputs == [] and c.runs == 0 and not c.can_run_code
    assert Reply("x").files == []
