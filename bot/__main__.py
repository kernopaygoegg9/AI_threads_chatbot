"""Command line entry point: `uv run python -m bot <command>`."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from . import content, jobs, replies, settings, threads, tokens
from .store import Store, now_utc


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_generate(args, st: Store) -> int:
    _print(jobs.generate_today(st, force=args.force))
    return 0


def cmd_tick(args, st: Store) -> int:
    """Everything the 15-minute cron does. Steps are isolated so one failure doesn't block the rest."""
    steps = {
        "sync_reviews": lambda: jobs.sync_reviews(st),
        "publish_due": lambda: jobs.publish_due(st),
        "replies": lambda: replies.process(st),
        "token": lambda: tokens.refresh_if_needed(st),
        "prune": lambda: st.prune_drafts(),
    }
    failed = False
    for name, step in steps.items():
        try:
            result = step()
            print(f"[{name}] ok: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")
        except Exception as e:
            failed = True
            st.log("tick_step_failed", step=name, error=str(e)[:300])
            print(f"[{name}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc()
    return 1 if failed else 0


def cmd_preview(args, st: Store) -> int:
    """Generate posts without saving anything — for tuning the persona."""
    use_news = {"on": True, "off": False}.get(args.news)
    for _ in range(args.count):
        try:
            _print(content.generate_post(st, use_news=use_news))
        except content.NoUsableCandidate as e:
            print(f"(no usable candidate: {e})")
    return 0


def cmd_draft(args, st: Store) -> int:
    """Create one post draft right now (scheduled for now) and route it through review."""
    _print(jobs.create_post_draft(st, now_utc(), use_news={"on": True, "off": False}.get(args.news)))
    return 0


def cmd_set_status(args, st: Store) -> int:
    fn = {"approve": jobs.approve, "reject": jobs.reject}[args.command]
    _print(fn(st, args.draft_id))
    return 0


def cmd_publish_now(args, st: Store) -> int:
    d = st.get_draft(args.draft_id)
    if not d:
        print("draft not found", file=sys.stderr)
        return 1
    _print(jobs.publish_draft(st, d))
    return 0


def cmd_status(args, st: Store) -> int:
    open_drafts = [d for d in st.drafts() if d["status"] in ("pending", "approved")]
    _print({"dry_run": settings.dry_run(), "meta": st.meta(), "open_drafts": open_drafts})
    return 0


def cmd_whoami(args, st: Store) -> int:
    _print({"me": threads.me(), "publishing_limit": threads.publishing_limit()})
    return 0


def cmd_exchange_token(args, st: Store) -> int:
    secret = settings.load_secrets().threads_app_secret
    if not secret:
        print("THREADS_APP_SECRET is not set", file=sys.stderr)
        return 1
    resp = threads.exchange_long_lived(args.short_token, secret)
    print("Long-lived token (store it as THREADS_ACCESS_TOKEN; do not commit it):")
    print(resp["access_token"])
    print(f"expires_in: {resp.get('expires_in')} seconds")
    return 0


def cmd_refresh_token(args, st: Store) -> int:
    print(tokens.refresh_if_needed(st, force=True))
    return 0


def cmd_ui(args, st: Store) -> int:
    import uvicorn

    from .ui import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m bot", description="Threads overlord bot")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("generate", help="create today's post drafts")
    s.add_argument("--force", action="store_true", help="generate even if already done today")
    s.set_defaults(fn=cmd_generate)

    sub.add_parser("tick", help="sync reviews, publish due drafts, reply to comments, refresh token").set_defaults(
        fn=cmd_tick
    )

    for name, fn, help_ in (
        ("preview", cmd_preview, "print sample posts without saving"),
        ("draft", cmd_draft, "create one draft now and send it to review"),
    ):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--news", choices=["auto", "on", "off"], default="auto")
        if name == "preview":
            s.add_argument("-n", "--count", type=int, default=1)
        s.set_defaults(fn=fn)

    for name in ("approve", "reject", "publish-now"):
        s = sub.add_parser(name, help=f"{name} a draft by id")
        s.add_argument("draft_id")
        s.set_defaults(fn=cmd_publish_now if name == "publish-now" else cmd_set_status)

    sub.add_parser("status", help="show open drafts and meta").set_defaults(fn=cmd_status)
    sub.add_parser("whoami", help="check Threads credentials").set_defaults(fn=cmd_whoami)
    sub.add_parser("refresh-token", help="force a token refresh").set_defaults(fn=cmd_refresh_token)

    s = sub.add_parser("exchange-token", help="turn a short-lived token into a 60-day token")
    s.add_argument("short_token")
    s.set_defaults(fn=cmd_exchange_token)

    s = sub.add_parser("ui", help="run the local web dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_ui)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args, Store())


if __name__ == "__main__":
    sys.exit(main())
