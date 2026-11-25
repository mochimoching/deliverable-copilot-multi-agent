"""Copilot CLI 呼び出し担当（第2段階ハーネス）。

`copilot -p --agent <役割> --model <固定モデル> --output-format json` を
新規プロセスで実行し、JSONL イベント列から最終応答テキスト・usage
（credits / tokens）・変更ファイル・成否を分離して返す。

credits は session.usage_checkpoint イベントの totalNanoAiu / 1e9。
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class CallResult:
    ok: bool
    text: str = ""
    credits: float = 0.0
    tokens: dict = field(default_factory=dict)
    seconds: float = 0.0
    exit_code: int | None = None
    files_modified: list = field(default_factory=list)
    error: str = ""
    fatal: bool = False  # 認証エラー・レート制限など、全体を止めるべき失敗
    raw_events: int = 0


FATAL_KEYWORDS = (
    "rate limit", "rate_limit", "too many requests", "429",
    "unauthorized", "401", "not logged in", "login required",
    "authentication", "session expired", "quota exceeded",
)


def _find_tokens(node, acc):
    """usage_checkpoint の data 内から tokenDetails / usage を再帰的に拾う。"""
    if isinstance(node, dict):
        td = node.get("tokenDetails")
        if isinstance(td, dict):
            for kind, v in td.items():
                if isinstance(v, dict) and "tokenCount" in v:
                    acc[kind] = acc.get(kind, 0) + int(v["tokenCount"])
        for key in ("inputTokens", "outputTokens", "cacheReadTokens",
                    "cacheWriteTokens", "reasoningTokens"):
            if key in node and isinstance(node[key], int):
                acc[key] = max(acc.get(key, 0), node[key])
        for v in node.values():
            _find_tokens(v, acc)
    elif isinstance(node, list):
        for v in node:
            _find_tokens(v, acc)


def parse_jsonl(stdout: str) -> dict:
    """JSONL 文字列を解析し、最終応答・usage・変更ファイルを抽出する。"""
    final_text = ""
    credits = 0.0
    tokens: dict = {}
    files_modified: list = []
    exit_code = None
    n_events = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        n_events += 1
        etype = ev.get("type", "")
        data = ev.get("data") or {}
        if etype == "assistant.message":
            content = data.get("content") or ""
            if content.strip():
                final_text = content
        elif etype == "session.usage_checkpoint":
            nano = data.get("totalNanoAiu")
            if isinstance(nano, (int, float)):
                credits = nano / 1e9
            acc: dict = {}
            _find_tokens(data, acc)
            if acc:
                tokens = acc
        elif etype == "result":
            exit_code = ev.get("exitCode")
            usage = ev.get("usage") or {}
            cc = usage.get("codeChanges") or {}
            files_modified = cc.get("filesModified") or []
    return {
        "text": final_text,
        "credits": credits,
        "tokens": tokens,
        "files_modified": files_modified,
        "exit_code": exit_code,
        "n_events": n_events,
    }


def run_copilot(
    copilot_bin: str,
    prompt: str,
    cwd: str,
    *,
    agent: str | None = None,
    model: str,
    allow_tools: tuple[str, ...] = (),
    deny_tools: tuple[str, ...] = (),
    timeout: int = 900,
    raw_log_path: str | None = None,
) -> CallResult:
    cmd = [
        copilot_bin, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-ask-user",
        "--no-auto-update",
    ]
    if agent:
        cmd += ["--agent", agent]
    for rule in allow_tools:
        cmd += ["--allow-tool", rule]
    for rule in deny_tools:
        cmd += ["--deny-tool", rule]

    started = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CallResult(ok=False, seconds=time.time() - started,
                          error=f"timeout after {timeout}s")
    seconds = time.time() - started

    if raw_log_path:
        with open(raw_log_path, "w", encoding="utf-8") as f:
            f.write(proc.stdout)
            if proc.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(proc.stderr)

    parsed = parse_jsonl(proc.stdout)
    exit_code = parsed["exit_code"]
    if exit_code is None:
        exit_code = proc.returncode
    ok = (exit_code == 0)
    error = ""
    fatal = False
    if not ok:
        blob = (proc.stderr or "") + "\n" + (parsed["text"] or "")
        error = (proc.stderr or "").strip()[-500:] or f"exit code {exit_code}"
        low = blob.lower()
        fatal = any(k in low for k in FATAL_KEYWORDS)
    return CallResult(
        ok=ok,
        text=parsed["text"],
        credits=parsed["credits"],
        tokens=parsed["tokens"],
        seconds=round(seconds, 1),
        exit_code=exit_code,
        files_modified=parsed["files_modified"],
        error=error,
        fatal=fatal,
        raw_events=parsed["n_events"],
    )
