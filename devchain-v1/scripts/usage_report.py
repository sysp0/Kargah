#!/usr/bin/env python3
"""Aggregate Claude Code transcript token usage (main + subagents)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def cwd_slug(cwd: Path) -> str:
    return str(cwd.resolve()).replace("/", "-").replace("_", "-")


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        print(f"warn: cannot read {path}: {e}", file=sys.stderr)
    return rows


def find_session(root: Path, session: str) -> tuple[Path, Path] | None:
    base = Path.home() / ".claude" / "projects" / cwd_slug(root)
    if not base.is_dir():
        return None
    if session == "latest":
        mains = sorted(base.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not mains:
            return None
        main = mains[0]
    else:
        main = base / f"{session}.jsonl"
        if not main.is_file():
            return None
    return main, base / main.stem / "subagents"


def map_agent_ids(main_rows: list[dict], sub_dir: Path) -> dict[str, str]:
    queue: list[str] = []
    mapping: dict[str, str] = {}
    for o in main_rows:
        msg = o.get("message")
        if isinstance(msg, dict):
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("name") == "Agent":
                    st = (c.get("input") or {}).get("subagent_type")
                    if st:
                        queue.append(st)
        tur = o.get("toolUseResult")
        if isinstance(tur, dict) and tur.get("agentId") and queue:
            mapping[str(tur["agentId"])] = queue.pop(0)
        att = o.get("attachment")
        if isinstance(att, dict) and att.get("hookEvent") == "SubagentStart":
            name = att.get("hookName") or ""
            if ":" in name and o.get("agentId"):
                mapping.setdefault(str(o["agentId"]), name.split(":", 1)[1])
    if sub_dir.is_dir():
        for path in sub_dir.glob("agent-*.jsonl"):
            for o in load_jsonl(path):
                att = o.get("attachment")
                if isinstance(att, dict) and att.get("hookEvent") == "SubagentStart":
                    name = att.get("hookName") or ""
                    if ":" in name and o.get("agentId"):
                        mapping.setdefault(str(o["agentId"]), name.split(":", 1)[1])
    return mapping


def parse_usage(msg: dict) -> dict[str, int] | None:
    u = msg.get("usage")
    if not isinstance(u, dict):
        return None
    cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    return {
        "input": int(u.get("input_tokens") or 0),
        "output": int(u.get("output_tokens") or 0),
        "cache_read": int(u.get("cache_read_input_tokens") or 0),
        "cache_creation": int(u.get("cache_creation_input_tokens") or 0),
        "ephemeral_5m": int(cc.get("ephemeral_5m_input_tokens") or 0),
        "ephemeral_1h": int(cc.get("ephemeral_1h_input_tokens") or 0),
    }


def add_row(agg: dict, agent: str, model: str, u: dict[str, int]) -> None:
    a = agg[(agent, model)]
    for k in u:
        a[k] += u[k]
    a["calls"] += 1
    peak = u["input"] + u["cache_read"] + u["cache_creation"]
    a["peak_ctx"] = max(a["peak_ctx"], peak)


def report(root: Path, session: str, prices_path: Path | None) -> int:
    found = find_session(root, session)
    if not found:
        print(f"no transcript for session={session!r}")
        print("warn: unknown layout or empty projects dir")
        return 0
    main_path, sub_dir = found
    main_rows = load_jsonl(main_path)
    if not main_rows:
        print(f"empty: {main_path}")
        return 0
    if "type" not in main_rows[0] and "message" not in main_rows[0]:
        print(f"warn: unexpected schema keys={sorted(main_rows[0])[:12]}")
        return 0
    id_map = map_agent_ids(main_rows, sub_dir)
    agg: dict = defaultdict(
        lambda: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
            "ephemeral_5m": 0,
            "ephemeral_1h": 0,
            "calls": 0,
            "peak_ctx": 0,
        }
    )
    for o in main_rows:
        if o.get("isSidechain") is True:
            continue
        msg = o.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            u = parse_usage(msg)
            if u:
                add_row(agg, "main", msg.get("model") or "?", u)
    if sub_dir.is_dir():
        for path in sorted(sub_dir.glob("agent-*.jsonl")):
            rows = load_jsonl(path)
            aid = next((str(o["agentId"]) for o in rows if o.get("agentId")), path.stem)
            agent = id_map.get(aid, path.stem)
            for o in rows:
                msg = o.get("message")
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    u = parse_usage(msg)
                    if u:
                        add_row(agg, agent, msg.get("model") or "?", u)
    prices = None
    if prices_path:
        try:
            prices = json.loads(prices_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"warn: prices: {e}", file=sys.stderr)
    print(f"session: {main_path.stem}")
    print(
        f"{'agent':<22} {'model':<22} {'in':>7} {'out':>7} "
        f"{'c_read':>7} {'c_creat':>7} {'e5m':>6} {'e1h':>6} {'calls':>5} {'peak':>7}"
    )
    for i, ((agent, model), row) in enumerate(sorted(agg.items())):
        if i >= 22:
            print("… truncated")
            break
        cost = ""
        if prices and model in prices:
            p = prices[model]
            try:
                dollars = (
                    row["input"] * float(p.get("input", 0))
                    + row["output"] * float(p.get("output", 0))
                    + row["cache_read"] * float(p.get("cache_read", 0))
                    + row["cache_creation"] * float(p.get("cache_creation", 0))
                ) / 1e6
                cost = f" ${dollars:.4f}"
            except (TypeError, ValueError):
                pass
        print(
            f"{agent:<22} {model:<22} {row['input']:>7} {row['output']:>7} "
            f"{row['cache_read']:>7} {row['cache_creation']:>7} "
            f"{row['ephemeral_5m']:>6} {row['ephemeral_1h']:>6} "
            f"{row['calls']:>5} {row['peak_ctx']:>7}{cost}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", default="latest")
    ap.add_argument("--prices", type=Path, default=None)
    ap.add_argument("--root", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        return report((args.root or Path.cwd()).resolve(), args.session, args.prices)
    except Exception as e:
        print(f"warn: usage_report failed: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
