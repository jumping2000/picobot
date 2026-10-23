import argparse
import asyncio
import logging
import sys

from .config import get_settings


def main() -> None:
    if sys.argv[1:2] == ["skills"]:   # amministrazione skill: non serve una chiave LLM
        from .skills_cli import main_skills
        sys.exit(main_skills(sys.argv[2:], get_settings()))
    p = argparse.ArgumentParser(prog="picobot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve", help="Telegram + API + scheduler")
    sv.add_argument("--no-telegram", action="store_true")
    sv.add_argument("--no-api", action="store_true")
    sub.add_parser("cli", help="REPL interattivo")
    sub.add_parser("skills", help="gestione skill: list | add | remove | validate | deps")
    args = p.parse_args()

    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                        level=logging.WARNING if args.cmd == "cli" else logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)   # il token Telegram e' nell'URL

    s = get_settings()
    if not s.api_key:
        sys.exit("OPENROUTER_API_KEY (o OPENAI_API_KEY) non configurata.")

    from . import runner

    if args.cmd == "cli":
        asyncio.run(runner.cli(s))
        return

    use_tg = not args.no_telegram and bool(s.telegram_bot_token)
    use_api = not args.no_api and s.api_enabled
    if use_tg and not s.allowed_ids and not s.allow_all_users:
        sys.exit("TELEGRAM_ALLOWED_USER_IDS vuoto: nessuno sarebbe autorizzato (o ALLOW_ALL_USERS=true).")
    if use_api and not s.token_map:
        logging.warning("API_TOKENS non configurato: API disattivata.")
        use_api = False
    if use_api and s.api_host not in {"127.0.0.1", "localhost"} and not s.api_ssl_certfile:
        logging.warning("API esposta senza TLS: il token viaggia in chiaro. Imposta API_SSL_CERTFILE/API_SSL_KEYFILE.")
    if not (use_tg or use_api):
        sys.exit("Nessun canale attivo: configura TELEGRAM_BOT_TOKEN e/o API_TOKENS.")
    asyncio.run(runner.serve(s, use_tg, use_api))


if __name__ == "__main__":
    main()
