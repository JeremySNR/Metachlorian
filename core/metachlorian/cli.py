"""Command line: ``metachlorian <command>``."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


def _lib(args):
    from .config import load_settings
    from .db import Database

    s = load_settings(args.data)
    s.ensure_dirs()
    return s, Database(s.db_path)


def cmd_init(args) -> None:
    from .config import load_settings

    s = load_settings(args.data)
    s.ensure_dirs()
    cfg = s.data_dir / "config.toml"
    if not cfg.exists():
        cfg.write_text("# Metachlorian configuration. See docs/configuration.md\nworkers = 2\n")
    print(f"Library ready at {s.data_dir}")


def cmd_serve(args) -> None:
    import uvicorn

    from .api.app import create_app
    from .config import load_settings

    s = load_settings(args.data)
    if args.host:
        s.host = args.host
    if args.port:
        s.port = args.port
    if args.workers is not None:
        s.workers = args.workers
    if not s.require_auth and s.host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("Refusing to listen on a network address without authentication. Set require_auth = true (team mode) "
                 "and create an admin with `metachlorian user add`, or bind to 127.0.0.1.")
    for src in args.add or []:
        from .db import Database
        from .ingest.scan import add_source

        add_source(Database(s.db_path), src)
    app = create_app(s, start_workers=not args.no_workers)
    print(f"Metachlorian {__import__('metachlorian').__version__} on http://{s.host}:{s.port}  (data: {s.data_dir})", flush=True)
    uvicorn.run(app, host=s.host, port=s.port, log_level="warning")


def cmd_add(args) -> None:
    from .ingest.scan import add_source, scan_source
    from .pipeline import plan_asset

    s, db = _lib(args)
    for uri in args.paths:
        sid = add_source(db, uri, watch=not args.no_watch)
        res = scan_source(db, sid, s.data_dir / "cache" / "s3")
        for aid in res.asset_ids or []:
            plan_asset(db, s, aid)
        print(json.dumps({"source": uri, **{k: v for k, v in res.as_dict().items() if k != "asset_ids"}}))


def cmd_import(args) -> None:
    """Download videos from web links into the library and wait for the downloads to finish."""
    import time

    from .ingest import importer

    s, db = _lib(args)
    ids = importer.enqueue(db, s, args.urls, args.folder or "", args.playlist, args.max_height, "cli")
    seen: set[int] = set()
    while True:
        rows = db.q("SELECT id, url, status, title, error, path FROM imports WHERE id IN ({0}) OR parent_id IN ({0})".format(",".join("?" * len(ids))),
                    (*ids, *ids))
        for r in rows:
            if r["status"] in ("done", "duplicate", "failed", "cancelled", "expanded") and r["id"] not in seen:
                seen.add(r["id"])
                print(json.dumps({k: r[k] for k in ("id", "status", "title", "path", "error") if r[k]}))
        if rows and all(r["status"] in ("done", "duplicate", "failed", "cancelled", "expanded") for r in rows):
            break
        time.sleep(1)
    print("Run `metachlorian serve` (or `process`) to analyse the new files.")


def cmd_process(args) -> None:
    from .pipeline import Worker, plan_all

    s, db = _lib(args)
    n = plan_all(db, s)
    print(f"planned {n} jobs")
    w = Worker(db, s)
    done = 0
    while True:
        r = w.run_once()
        if r is None:
            break
        done += 1
        if args.verbose:
            print(r, flush=True)
    from .jobs.queue import throughput

    print(json.dumps({"jobs_run": done, **throughput(db)}, indent=1))


def cmd_status(args) -> None:
    from .jobs.queue import stats, throughput

    s, db = _lib(args)
    a = db.q1("SELECT COUNT(*) n, SUM(duration) d FROM assets WHERE deleted_at IS NULL")
    print(json.dumps({"assets": a["n"], "hours": round((a["d"] or 0) / 3600, 3), "shots": db.q1("SELECT COUNT(*) n FROM shot_index")["n"],
                      "jobs": stats(db)["by_status"], "throughput": throughput(db)}, indent=1))


def cmd_search(args) -> None:
    from .search.engine import SearchEngine, SearchRequest

    s, db = _lib(args)
    r = SearchEngine(db, s).search(SearchRequest(q=" ".join(args.query), limit=args.limit))
    for x in r["results"]:
        print(f"{x['filename'][:28]:28s} {x['start']:8.2f}-{x['end']:8.2f}  {(x['caption'] or '')[:80]}")
    print(f"{r['total']} results in {r['timings_ms']['total']} ms; parsed: {json.dumps({k: v for k, v in r['query']['parsed'].items() if v and k != 'text'})}")


def cmd_user(args) -> None:
    from . import auth

    s, db = _lib(args)
    if args.action == "add":
        pw = args.password or os.environ.get("METACHLORIAN_PASSWORD")
        uid = auth.create_user(db, args.username, args.role, pw)
        print(f"created {args.role} '{args.username}' (id {uid})")
    elif args.action == "list":
        for r in db.q("SELECT id, username, role, disabled FROM users"):
            print(dict(r))


def cmd_token(args) -> None:
    from . import auth

    s, db = _lib(args)
    u = db.q1("SELECT id FROM users WHERE username=?", (args.username,))
    uid = u["id"] if u else auth.create_user(db, args.username, "agent")
    tok = auth.create_token(db, uid, args.name, args.scopes.split(",") if args.scopes else None)
    print(tok)


def cmd_mcp(args) -> None:
    from .mcp_server.server import run_stdio
    from .service import Library

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    s, db = _lib(args)
    run_stdio(Library(db, s), os.environ.get("METACHLORIAN_TOKEN"))


def cmd_models(args) -> None:
    from . import models

    s, _ = _lib(args)
    root = s.resolved_models_dir
    if args.action == "list":
        for m in models.status(root):
            print(f"{'✓' if m['installed'] else '·'} {m['name']:28s} {m['licence']:12s} {m['size_mb']:>6} MB  {m['purpose']}")
    elif args.action == "fetch":
        names = args.names or [n for n, sp in models.SPECS.items() if sp.default]
        for n in names:
            print(f"fetching {n} …", flush=True)
            models.fetch(root, n)
    elif args.action == "install-from":
        for n in args.names[1:] or list(models.SPECS):
            try:
                models.install_from(root, n, Path(args.names[0]))
                print(f"installed {n}")
            except FileNotFoundError as e:
                print(f"skip {n}: {e}")


def cmd_reindex(args) -> None:
    from .indexer import reindex_all

    s, db = _lib(args)
    print(f"indexed {reindex_all(db, s)} shots")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="metachlorian", description="Self-hostable video library that understands every shot.")
    ap.add_argument("--data", default=os.environ.get("METACHLORIAN_DATA"), help="library directory (default ~/.local/share/metachlorian)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sp = sub.add_parser("serve", help="run the core: API, MCP, web app and analysis workers")
    sp.add_argument("--host")
    sp.add_argument("--port", type=int)
    sp.add_argument("--workers", type=int)
    sp.add_argument("--no-workers", action="store_true")
    sp.add_argument("--add", nargs="*", help="watch folders or s3:// sources to add")
    sp.set_defaults(fn=cmd_serve)
    sp = sub.add_parser("import", help="download videos from web links (YouTube, Vimeo...) into the library")
    sp.add_argument("urls", nargs="+")
    sp.add_argument("--folder", help="subfolder of <library>/imports, e.g. 'Disney 2026' (default: the site's name)")
    sp.add_argument("--playlist", action="store_true", help="import every video of a playlist or channel link")
    sp.add_argument("--max-height", type=int, help="quality cap: 720, 1080 (default), 2160...")
    sp.set_defaults(fn=cmd_import)
    sp = sub.add_parser("add", help="add a folder or s3:// bucket and scan it")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--no-watch", action="store_true")
    sp.set_defaults(fn=cmd_add)
    sp = sub.add_parser("process", help="run all pending analysis in this process, then exit")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(fn=cmd_process)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("reindex").set_defaults(fn=cmd_reindex)
    sp = sub.add_parser("search")
    sp.add_argument("query", nargs="+")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("user")
    sp.add_argument("action", choices=["add", "list"])
    sp.add_argument("username", nargs="?")
    sp.add_argument("--role", default="editor", choices=["viewer", "editor", "admin", "agent"])
    sp.add_argument("--password")
    sp.set_defaults(fn=cmd_user)
    sp = sub.add_parser("token", help="create an API/MCP token")
    sp.add_argument("username")
    sp.add_argument("--name", default="agent")
    sp.add_argument("--scopes", help="comma-separated, e.g. library:read,media:export")
    sp.set_defaults(fn=cmd_token)
    sub.add_parser("mcp", help="MCP server on stdio (read-only unless METACHLORIAN_TOKEN grants more)").set_defaults(fn=cmd_mcp)
    sp = sub.add_parser("models")
    sp.add_argument("action", choices=["list", "fetch", "install-from"])
    sp.add_argument("names", nargs="*")
    sp.set_defaults(fn=cmd_models)
    args = ap.parse_args(argv)
    logging.basicConfig(level=os.environ.get("METACHLORIAN_LOG", "WARNING"))
    args.fn(args)


if __name__ == "__main__":
    main()
