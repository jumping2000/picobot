"""Finto server OpenAI-compatibile (porta 8765) per test senza API key. Registra ogni chiamata in LOG."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG: list[dict] = []
ROUTES = {"quotazione": "finance", "programma": "coder", "cerca": "web", "complesso": "complexteam"}


def _tool_call(name, args, cid="c1"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LOG.append(body)
        msgs, names = body["messages"], [t["function"]["name"] for t in body.get("tools") or []]
        last = msgs[-1]
        user = next((m["content"] for m in reversed(msgs) if m["role"] == "user" and isinstance(m["content"], str)), "").lower()
        msg = {"role": "assistant", "content": "RISPOSTA-FINTA"}
        tool_out = [str(m.get("content")) for m in msgs if m["role"] == "tool"]
        if "documento" in user and "deliver_file" in names:           # Analyst: crea il file, poi lo consegna
            if any("Consegnato" in o for o in tool_out):
                msg = {"role": "assistant", "content": "File creato e consegnato."}
            elif any("exit=0" in o for o in tool_out):
                msg = _tool_call("deliver_file", {"path": "outputs/e2e città.docx"}, "c3")
            else:
                msg = _tool_call("run_node", {"code": "require('fs').writeFileSync('outputs/e2e città.docx','PK')"}, "c2")
        elif last["role"] != "tool" and "documento" in user and "delegate_task_to_member" in names:
            member = "analyst" if "list_skills" in names else "complexteam"   # leader del ComplexTeam vs router
            msg = _tool_call("delegate_task_to_member", {"member_id": member, "task": user})
        elif last["role"] != "tool":
            if "delegate_task_to_member" in names and any(k in user for k in ROUTES):
                member = next(v for k, v in ROUTES.items() if k in user)
                msg = _tool_call("delegate_task_to_member", {"member_id": member, "task": user})
            elif "add" in names and "somma" in user:          # tool MCP del server di prova
                msg = _tool_call("add", {"a": 2, "b": 3})
            elif "run_node" in names and "esegui node" in user:
                msg = _tool_call("run_node", {"code": "console.log(42)"})
            elif "run_python" in names and "programma" in user:
                msg = _tool_call("run_python", {"code": "print(6*7)"})
            elif "add_memory" in names:     # chiamata interna del MemoryManager
                msg = _tool_call("add_memory", {"memory": "Si chiama Gianpi", "topics": ["identita"]})
            elif "update_user_memory" in names and "ricorda" in user:   # il router decide di salvare
                msg = _tool_call("update_user_memory", {"task": "Ricorda: l'utente si chiama Gianpi"})
        out = {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
               "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop"}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def start(port=8765):
    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
