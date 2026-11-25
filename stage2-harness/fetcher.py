"""GitHub issue 取得担当（第2段階ハーネス）。

取得は同梱の github_client.py（標準ライブラリのみ）で行い、外部の
プロジェクトには依存しない。認証は環境変数 GITHUB_TOKEN が本線で、
未設定の場合のみ Muse 環境専用のフォールバック（custom.github
コネクタ経由）を使う。詳細は github_client.py の冒頭を参照。

保存先はハーネス自前の inputs/ 配下で、レイアウトは従来の input_base と
同一（<repo>/<milestone>/<state>/current/markdown/{issues,issues_diff}）
にそろえ、input_base の意味を変えずに差し替えられるようにする。
出力形式（issue_markdown）は従来実装とバイト単位で互換に保つ。
"""
from __future__ import annotations

import os

from github_client import GitHubClient, normalize_issue

HERE = os.path.dirname(os.path.abspath(__file__))


def issue_markdown(issue):
    """個別issue Markdown（従来実装と同一形式）。"""
    lines = [
        f"# {issue['title']}",
        "",
        f"**Issue番号**: #{issue['number']}",
        f"**状態**: {issue['state']} | **作成者**: {issue['author']} | **作成日**: {issue['created_at'][:10]}",
    ]
    if issue["labels"]:
        lines.append(f"**ラベル**: {', '.join(issue['labels'])}")
    if issue["milestone"]:
        lines.append(f"**マイルストーン**: {issue['milestone']}")
    lines += [f"**URL**: {issue['url']}", "", "## 内容", "", issue["body"]]
    if issue["comments"]:
        lines += ["", "## コメント"]
        for i, c in enumerate(issue["comments"], 1):
            lines += ["", f"### コメント {i} by {c['author']} ({c['created_at'][:10]})",
                      "", c["body"]]
    return "\n".join(lines) + "\n"


def inputs_markdown_dir(cfg: dict) -> str:
    """取得結果の保存先（markdown ルート）。input_base と同じ相対構造。"""
    f = cfg["fetch"]
    milestone = f.get("milestone") or "all"
    return os.path.join(HERE, "inputs", f["repo"], milestone,
                        f["state"], "current", "markdown")


def effective_input_base(cfg: dict) -> str:
    """入力の実効ルート。

    config.input_base が文字列で指定されていれば従来どおりそのフォルダ
    （外部で取得済みのデータ）を指す。null なら自前取得の inputs/ を使う。
    """
    base = cfg.get("input_base")
    if base:
        return base
    return inputs_markdown_dir(cfg)


def _write_diff(diff_dir: str, issue: dict, closing: dict,
                client: GitHubClient, max_diff_size: int) -> bool:
    """closing PR / commit の diff を従来形式で保存する。"""
    if closing["type"] == "pr":
        text, url = client.get_pr_diff(closing["number"], max_diff_size)
        ref = f"PR #{closing['number']} ({closing['created_at']})"
    else:
        text, url = client.get_commit_diff(closing["sha"], max_diff_size)
        ref = f"Commit {closing['sha'][:12]} ({closing['created_at']})"
    truncated = len(text) > max_diff_size
    if truncated:
        text = text[:max_diff_size]
    content = (f"Issue #{issue['number']}: {issue['title']}\n"
               f"Reference: {ref}\nURL: {url}\n\n--- Diff ---\n{text}\n")
    if truncated:
        content += f"\n[Warning: Diff truncated at {max_diff_size} characters]\n"
    os.makedirs(diff_dir, exist_ok=True)
    with open(os.path.join(diff_dir, f"issue_{issue['number']}.txt"),
              "w", encoding="utf-8") as f:
        f.write(content)
    return True


def fetch_missing(cfg: dict, force: bool = False,
                  numbers: list[int] | None = None,
                  log=print) -> dict:
    """未取得の issue を GitHub から取得して inputs/ に保存する。

    numbers が明示された場合はその番号だけを対象にし、exclude_issues は
    適用しない（明示指定を優先）。numbers が無い場合は fetch 設定の
    repo/milestone/state/order で一覧を取得し、exclude_issues を除いた
    件を対象にする。既にファイルがある件は再取得しない（force のみ例外）。

    エラー（レート制限含む）が発生したら、その時点で残りを中止して
    結果を返す（粘らない）。
    """
    f = cfg["fetch"]
    md_dir = inputs_markdown_dir(cfg)
    issues_dir = os.path.join(md_dir, "issues")
    diff_dir = os.path.join(md_dir, "issues_diff")
    os.makedirs(issues_dir, exist_ok=True)

    client = GitHubClient(f["owner"], f["repo"])
    raw_map: dict[int, dict] = {}
    if numbers:
        targets = list(numbers)
    else:
        raws = client.list_issues(
            state=f["state"],
            milestone=f.get("milestone") or "*",
            max_issues=f.get("max_issues", 100),
            order=f.get("order", "desc"),
        )
        raw_map = {r["number"]: r for r in raws}
        exclude = set(cfg.get("exclude_issues", []))
        targets = sorted(n for n in raw_map if n not in exclude)

    result = {"targets": targets, "fetched": [], "skipped": [],
              "errors": [], "dir": md_dir}
    for n in targets:
        dst = os.path.join(issues_dir, f"issue_{n}.md")
        if os.path.exists(dst) and not force:
            result["skipped"].append(n)
            continue
        try:
            raw = raw_map.get(n) or client.get_issue(n)
            comments = client.get_comments(n, f.get("max_comments", 20))
            try:
                closing = client.find_closing_reference(n)
            except Exception:
                closing = None
            issue = normalize_issue(raw, comments, closing)
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(issue_markdown(issue))
            if closing:
                _write_diff(diff_dir, issue, closing, client,
                            f.get("max_diff_size", 50000))
            result["fetched"].append(n)
            log(f"    [fetch] #{n} 取得 (comments={len(issue['comments'])}, "
                f"diff={'あり' if closing else 'なし'})")
        except Exception as e:  # レート制限・認証エラー等は粘らず止める
            result["errors"].append({"issue": n, "error": str(e)[:300]})
            log(f"    [fetch] #{n} でエラー。中止します: {str(e)[:200]}")
            break
    return result
