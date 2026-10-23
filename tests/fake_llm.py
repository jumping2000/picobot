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
        if last["role"] != "tool":
            if "delegate_task_to_member" in names and any(k in user for k in ROUTES):
                member = next(v for k, v in ROUTES.items() if k in user)
                msg = _tool_call("delegate_task_to_member", {"member_id": member, "task": user})
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
