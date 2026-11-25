"""第2段階ハーネス — 進行役。

設計書（stage2-harness-design.md）に基づく実装。
取得（fetcher.py）→ translator → planner → writer → reviewer → fixer を
件ごとに新規プロセスで直列に回し、決定的検証（validate.py）を通った
件だけを done にする一気通貫の基盤。
役割の基準は、ユーザーのガイドライン正本（config の guidelines_dir、
既定は github_issue_translate の TRANSLATION / SUMMARY / REVIEW の
各ガイドライン）をプロンプトに全文埋め込んで渡す。AI明示と #参照の
リンク化はモデルに任せず、ハーネスの決定的後処理で適用する
（Claude 側パイプラインと同じ分担）。
状態は runs/state.json（原子的更新）、呼び出し記録は runs/run-log.jsonl
（追記型）に即時永続化し、中断・再起動からは state だけで再開できる。

使い方:
    python3 harness.py                 # 残件をすべて実行（必要なら取得から）
    python3 harness.py --limit 2       # 先頭2件だけ（小規模確認用）
    python3 harness.py --items 5158,5514
    python3 harness.py --reset-failed  # failed の件を pending に戻して再実行
    python3 harness.py --status        # 進捗だけ表示
    python3 harness.py --fetch-only    # GitHub からの取得だけを行う
    python3 harness.py --fetch-only --fetch-numbers 5158,5570  # 番号指定で取得
    python3 harness.py --backfill-translate  # done 済みの件に翻訳だけ補完
    python3 harness.py --retranslate-titles  # タイトルが未訳の件だけ翻訳を再実行
    python3 harness.py --runs-dir runs-e2e   # 状態一式を別フォルダで実行
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import validate as V  # noqa: E402
import fetcher  # noqa: E402
from copilot_runner import run_copilot  # noqa: E402

RUNS_DIR = os.path.join(HERE, "runs")
STATE_PATH = os.path.join(RUNS_DIR, "state.json")
LOG_PATH = os.path.join(RUNS_DIR, "run-log.jsonl")
CONFIG_PATH = os.path.join(HERE, "config.json")

READ_ONLY_ALLOW = ("read",)
READ_ONLY_DENY = ("shell", "write")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state(cfg: dict) -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {
        "version": 1,
        "model": cfg["model"],
        "created": now_iso(),
        "budget_warned": False,
        "items": {},
    }


def save_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


def append_log(entry: dict) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_total_credits() -> float:
    total = 0.0
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    total += float(json.loads(line).get("credits", 0.0))
    return total


def log_item_credits(item: str) -> float:
    total = 0.0
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                if e.get("item") == item:
                    total += float(e.get("credits", 0.0))
    return total


def discover_items(cfg: dict) -> list[int]:
    issues_dir = os.path.join(fetcher.effective_input_base(cfg), "issues")
    if not os.path.isdir(issues_dir):
        return []
    nums = []
    for name in os.listdir(issues_dir):
        if name.startswith("issue_") and name.endswith(".md"):
            nums.append(int(name[len("issue_"):-len(".md")]))
    exclude = set(cfg.get("exclude_issues", []))
    return sorted(n for n in nums if n not in exclude)


# ---------------------------------------------------------------- guidelines
_GUIDELINES: dict = {}


def load_guidelines(cfg: dict) -> dict:
    """ガイドライン正本（config の guidelines_dir）を読み込む。

    正本は1か所（既定は ~/workspace/github_issue_translate）だけに置き、
    Claude 側パイプラインと同じく、プロンプトに全文を埋め込んで渡す。
    """
    global _GUIDELINES
    if _GUIDELINES:
        return _GUIDELINES
    base = os.path.expanduser(cfg.get("guidelines_dir") or "")
    if base and not os.path.isabs(base):
        base = os.path.join(HERE, base)
    files = cfg.get("guideline_files") or {
        "translation": "TRANSLATION_GUIDELINE.md",
        "summary": "SUMMARY_GUIDELINE.md",
        "review": "REVIEW_GUIDELINE.md",
    }
    out = {}
    for key, name in files.items():
        path = os.path.join(base, name)
        with open(path, encoding="utf-8") as f:
            out[key] = f.read()
    _GUIDELINES = out
    return out


# ガイドライン内の記述とハーネスの実行契約が衝突する場合の優先順位の明示。
# Claude 側パイプラインでも、AI明示やリンク化はモデルに任せず後処理で
# 決定的に適用している。ここでも同じ分担にする。
_PRECEDENCE = (
    "【優先順位の明示】ガイドライン本文中にある出力ディレクトリ・ファイル名・"
    "パラメータ（temperature / max_tokens 等）に関する記述は、この実行では"
    "適用しません。以下の「実行契約」（読み書きするファイル名、AI明示と"
    "#参照リンク化の扱い、出力形式）が優先します。\n"
)


def _embed(title: str, guideline: str) -> str:
    return (f"===== ガイドライン開始（{title}） =====\n"
            f"{guideline}\n"
            f"===== ガイドライン終了（{title}） =====\n")


# ---------------------------------------------------------------- prompts
def translator_prompt(guideline: str, retry_note: str = "") -> str:
    return (
        "あなたは技術文書の翻訳に特化した翻訳アシスタントです。\n"
        "このフォルダにある input_issue.md（GitHub issue 原文）を read ツールで"
        "読み、以下の翻訳ガイドライン（TRANSLATION_GUIDELINE.md）の全文に"
        "従って、本文とコメントのすべてを日本語に全文翻訳し、translated.md に "
        "write ツールで作成してください。\n"
        "翻訳スタイル: バランス型（ガイドラインの推奨）\n"
        + _PRECEDENCE +
        "実行契約:\n"
        "- 出力先は translated.md です（ガイドライン記載の出力ディレクトリは"
        "使いません）。\n"
        "- AI明示（「このドキュメントは生成AI...」の行）は書かないでください。"
        "明示はハーネスが後処理で付与します。\n"
        "- 要約・抜粋・省略はしない。全量を訳すこと。\n"
        "- issue タイトル（先頭の見出し）も必ず日本語に翻訳すること。"
        "英語のまま残さないこと。ただしタイトル内のコード・クラス名・"
        "メソッド名などの識別子は原文のまま保持し、それ以外の部分を訳すこと。"
        "タイトルにバッククォートは付けないこと。\n"
        "- 見出しの構造（# のレベルと順序）は原文どおりに保つこと。\n"
        "- メタ情報の行（**Issue番号**、**状態**、**作成者**、**作成日**、"
        "**ラベル**、**マイルストーン**、**URL**）は原文の形式のまま残すこと。\n"
        "- コードブロック（``` で囲まれた範囲）の中身は一字一句そのまま"
        "コピーすること。インラインコード、クラス名・メソッド名・ファイル名、"
        "URL は原文のまま保持すること。\n"
        "- #番号 の issue 参照はリンク化せず原文のまま保持すること"
        "（リンク化はハーネスが後処理で決定的に行います）。\n"
        "- コメント見出し（### コメント N by ユーザー名 (日付)）の形式は"
        "原文のままにすること。\n"
        "- 原文にない情報を補わないこと。\n"
        + _embed("TRANSLATION_GUIDELINE.md", guideline) +
        "作業後に、翻訳した旨だけを短く返してください。"
        + retry_note
    )


def planner_prompt(guideline: str, retry_note: str = "") -> str:
    return (
        "このフォルダにある translated.md（翻訳済みの issue。本文・コメントの"
        "全文訳）と、あれば input_diff.txt（対応する修正差分）を read ツールで"
        "読んでください。translated.md が無い場合は input_issue.md を"
        "読んでください。\n"
        "目的は、この issue への修正を、以下の要約ガイドライン"
        "（SUMMARY_GUIDELINE.md）の想定読者（ペルソナ）と構成に沿って"
        "日本語で要約する記事を作ることです。あなたは計画だけを作ります。"
        "要約本文は書かないでください。ファイルも作らないでください。\n"
        + _PRECEDENCE +
        "実行契約:\n"
        "- 計画は次の5項目構成で、本文テキストとしてのみ返してください。\n"
        "1. 要件の要約\n"
        "2. 前提と未確認点\n"
        "3. 影響範囲\n"
        "4. 実装手順（writer が要約を書く手順）\n"
        "5. 検証方法\n"
        "- 実装手順には、ガイドラインの構成（課題概要／原因／対応方針、"
        "バグの場合のみバグの発生タイミング）、表や図（PlantUML）の活用可否、"
        "issue 本文と diff の齟齬の確認を含めること。\n"
        "- 入力にない情報を推測で補わないこと。不確かな点は「前提と未確認点」"
        "に挙げること。\n"
        + _embed("SUMMARY_GUIDELINE.md", guideline)
        + retry_note
    )


def writer_prompt(num: int, sections: list[str], guideline: str,
                  bug_section: str, is_bug: bool,
                  retry_note: str = "") -> str:
    heads = "\n".join(f"## {s}" for s in sections)
    if is_bug:
        bug_note = (
            f"- この issue はバグ（type: bug ラベル）です。ガイドラインに従い"
            f"「## {bug_section}」（バグが発生した Spring Batch のバージョン、"
            "バグが発生したコミットへのリンク）も追加してください。\n")
    else:
        bug_note = (
            f"- 「## {bug_section}」は、バグと判断できる場合のみ追加して"
            "ください（この issue にバグ系ラベルはありません）。\n")
    return (
        "このフォルダの translated.md（翻訳済み issue）、input_diff.txt"
        "（無い場合もある）、plan.md を read ツールで読んでください。"
        "translated.md が無い場合は input_issue.md を読んでください。\n"
        "plan.md の計画に沿って、以下の要約ガイドライン"
        "（SUMMARY_GUIDELINE.md）の全文に従い、日本語要約を draft.md に "
        "write ツールで作成してください。\n"
        + _PRECEDENCE +
        "実行契約:\n"
        "- 出力先は draft.md です。AI明示（「このドキュメントは生成AI...」の"
        "行）は書かないでください（ハーネスが後処理で付与します）。\n"
        "- 先頭にタイトル行（# の見出し）は付けず、本文は「## 課題概要」"
        "から始めてください。\n"
        "- 見出し構成は次を基本としてください（見出しは一字一句このとおり）:\n"
        f"{heads}\n"
        + bug_note +
        "- 対応方針には diff の解析結果を統合し、issue 本文と diff の内容に"
        "齟齬がある場合はその旨を明記してください。diff が無い場合は本文のみ"
        "から書いてください。\n"
        "- クラス名・メソッド名はバッククォートで囲み、Issue参照はリンク"
        "形式を維持してください。入力にない情報を書かないこと。断定できない"
        "ことは推測と分かるように書くこと。\n"
        + _embed("SUMMARY_GUIDELINE.md", guideline) +
        "作業後に、変更内容の要約だけを短く返してください。"
        + retry_note
    )


def reviewer_prompt(guideline: str, retry_note: str = "") -> str:
    return (
        "あなたはレビュー担当です。自分では要約を書き直さず、問題点と"
        "具体的な修正指示だけを返してください。\n"
        "【レビューの立脚点】このレビューは、想定読者ペルソナ（Spring Batch "
        "を業務で2〜3年使う中堅エンジニア）として要約を読んだときの"
        "チェックです。「この読者が、つまずかずに読めるか」「自分の業務に"
        "どう効くか分かるか」を終始の判断軸にしてください。\n"
        "【観点の優先順位】中心はペルソナにとっての (1) 難しさ（用語と"
        "前提知識）、(2) 堅苦しさ（文体）、(3) 業務への効き方です。"
        "(4) 冗長さと構成、(5) 形式ルールは、その次に確認してください。\n"
        "このフォルダの draft.md（要約の下書き）を read ツールで読んで"
        "ください。必要に応じて translated.md と input_diff.txt も参照して"
        "ください。ファイルは作らないでください。\n"
        "以下のレビューガイドライン（REVIEW_GUIDELINE.md）の全文に従って"
        "点検してください。\n"
        "【優先順位の明示】出力形式については、ガイドライン記載の JSON "
        "形式ではなく、下記のハーネス出力契約を優先してください。\n"
        "【ハーネス出力契約】レビュー結果は、次のスキーマの JSON のみで"
        "返してください。前後に文章を付けないでください。\n"
        '{"verdict": "pass" または "revise", "issues": [{"severity": "must" | '
        '"should" | "nit", "location": "対象箇所", "reason": "ペルソナの立場で'
        '何が問題か", "fix": "具体的な修正指示（どこを・どう直すか）"}]}\n'
        "問題がなければ verdict は \"pass\"、issues は空配列にしてください。"
        "「もっと分かりやすく」のような曖昧な指摘は禁止です。必ず、どこを・"
        "どう直すかまで書いてください。\n"
        + _embed("REVIEW_GUIDELINE.md", guideline)
        + retry_note
    )


def fixer_prompt(retry_note: str = "") -> str:
    return (
        "このフォルダの draft.md と review.json を read ツールで読んでください。\n"
        "review.json の issues に挙げられた箇所だけを修正し、結果を final.md に "
        "write ツールで作成してください。issues にない改善はしないでください。\n"
        "見出し構成（## 課題概要、## 原因、## 対応方針、あれば "
        "## バグの発生タイミング）は変えないでください。AI明示の行は"
        "付けないでください（ハーネスが後処理で付与します）。\n"
        "作業後に、修正した箇所の要約だけを短く返してください。"
        + retry_note
    )


# ---------------------------------------------------------------- helpers
class FatalRun(Exception):
    """認証エラー・レート制限など、実行全体を止めるべき事態。"""


def call_role(cfg, state, item_key, role, prompt, workdir,
              allow=(), deny=(), attempt=1):
    """1役割を呼び出し、run-log と state に即時記録して結果を返す。"""
    # 生ログは logs/ サブフォルダに置く（検証8のスナップショットは
    # 作業フォルダ直下のファイルだけを見るため、ハーネス自身の
    # 書き込みを役割の変更と誤検出しない）
    logs_dir = os.path.join(workdir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    raw_log = os.path.join(logs_dir, f"stdout-{role}.jsonl")
    if attempt > 1:
        raw_log = os.path.join(logs_dir, f"stdout-{role}-try{attempt}.jsonl")
    result = run_copilot(
        cfg["copilot_bin"], prompt, workdir,
        agent=role, model=cfg["model"],
        allow_tools=allow, deny_tools=deny,
        timeout=cfg["call_timeout_sec"], raw_log_path=raw_log,
    )
    append_log({
        "ts": now_iso(), "item": item_key, "role": role, "attempt": attempt,
        "model": cfg["model"], "credits": round(result.credits, 4),
        "tokens": result.tokens, "seconds": result.seconds,
        "ok": result.ok, "exit_code": result.exit_code,
        "error": result.error or None,
    })
    rec = state["items"][item_key]
    prev = rec["roles"].get(role, {})
    rec["roles"][role] = {
        "ok": result.ok,
        # リトライ分も含めて累積する（run-log の合計と一致させるため）
        "credits": round(prev.get("credits", 0.0) + result.credits, 4),
        "seconds": round(prev.get("seconds", 0.0) + result.seconds, 1),
        "attempts": attempt,
        "error": result.error or None,
    }
    rec["credits_total"] = round(
        sum(r.get("credits", 0.0) for r in rec["roles"].values()), 4)
    save_state(state)
    print(f"    [{role}] ok={result.ok} credits={result.credits:.2f} "
          f"{result.seconds:.0f}s" + (f" error={result.error[:120]}" if result.error else ""))
    if not result.ok and result.fatal:
        raise FatalRun(f"{role}: {result.error}")
    return result


def fail_item(state, item_key, reason):
    rec = state["items"][item_key]
    rec["status"] = "failed"
    rec["failure"] = reason
    rec["finished"] = now_iso()
    save_state(state)
    print(f"    !! FAILED: {reason}")


def clean_plan_text(text: str) -> tuple[str, bool]:
    """planner 応答の前置き（トレース等）を、最初の "1." 行までで切り落とす。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("1.") and "要件の要約" in line:
            if i > 0:
                return "\n".join(lines[i:]).strip() + "\n", True
            return text.strip() + "\n", False
    return text.strip() + "\n", False


# ---------------------------------------------------------------- translator
def run_translator_step(cfg, state, num: int, workdir: str) -> bool:
    """translator を呼び、translated.md を作って決定的検証まで行う。

    成否は state の rec["translation"] に記録する（件の status は触らない。
    status 遷移は呼び出し側の責務）。戻り値: 成功したら True。
    """
    key = str(num)
    rec = state["items"][key]
    issue_path = os.path.join(workdir, "input_issue.md")
    translated_path = os.path.join(workdir, "translated.md")
    with open(issue_path, encoding="utf-8") as f:
        original = f.read()
    guideline = load_guidelines(cfg)["translation"]
    fetch_cfg = cfg.get("fetch", {})
    retries = cfg["format_retries"]
    note = ""
    last_det: dict = {}
    for attempt in range(1, retries + 2):
        if os.path.exists(translated_path):
            os.remove(translated_path)
        res = call_role(cfg, state, key, "translator",
                        translator_prompt(guideline, note),
                        workdir,
                        allow=("read", f"write({translated_path})"),
                        deny=("shell",), attempt=attempt)
        if not res.ok:
            rec["translation"] = {"status": "failed",
                                  "reason": f"translator 呼び出し失敗: {res.error}"}
            save_state(state)
            return False
        if not os.path.exists(translated_path):
            note = ("\n\n注意：前回は translated.md が作成されませんでした。"
                    "write ツールで translated.md を作成してください。")
            continue
        with open(translated_path, encoding="utf-8") as f:
            translated_raw = f.read()
        # AI明示はモデルに書かせない。混入していたら除去して素の本文に戻し、
        # 検証を通った後にハーネスが後処理で付与し直す（Claude 側と同じ分担）
        translated = V.strip_attributions(translated_raw)
        ok, det = V.validate_translation(
            original, translated, cfg.get("translation_min_ratio", 0.35))
        last_det = det
        if ok:
            # 決定的後処理：#参照のリンク化（コードフェンス外のみ）＋
            # AI明示を冒頭にちょうど1行付与する
            body = V.linkify(translated, fetch_cfg.get("owner", ""),
                             fetch_cfg.get("repo", ""))
            final_text = (V.attribution_line(cfg["model"], "translation",
                                             date.today())
                          + "\n\n" + body.strip("\n") + "\n")
            a_ok, a_det = V.validate_attribution(final_text, "translation")
            det["attribution"] = a_det
            det["postprocess"] = {"linkify": True, "attribution": a_ok}
            if not a_ok:
                rec["translation"] = {"status": "failed",
                                      "reason": "AI明示の後処理に失敗",
                                      "validation": det}
                save_state(state)
                return False
            with open(translated_path, "w", encoding="utf-8") as f:
                f.write(final_text)
            rec["translation"] = {"status": "done", "validation": det}
            save_state(state)
            return True
        note = ("\n\n注意：前回の翻訳は検証に合格しませんでした"
                f"（{'; '.join(det.get('errors', []))}）。"
                "コードブロックは原文のまま一字一句コピーし、見出し構造を"
                "原文どおりに保ち、タイトル（先頭の見出し）も日本語に訳し、"
                "省略せず全文を訳し直してください。")
    rec["translation"] = {"status": "failed",
                          "reason": "翻訳検証に不合格（リトライ後も）",
                          "validation": last_det}
    save_state(state)
    return False


# ---------------------------------------------------------------- item flow
def process_item(cfg, state, num: int) -> None:
    key = str(num)
    base = fetcher.effective_input_base(cfg)
    workdir = os.path.join(RUNS_DIR, f"issue_{num}")
    os.makedirs(workdir, exist_ok=True)
    rec = state["items"].setdefault(key, {
        "status": "pending", "roles": {}, "credits_total": 0.0,
        "verdict": None, "validation": {}, "failure": None, "warnings": [],
    })
    if rec["status"] == "pending":
        rec["started"] = now_iso()

    # --- 入力の組み立て
    issue_src = os.path.join(base, "issues", f"issue_{num}.md")
    diff_src = os.path.join(base, "issues_diff", f"issue_{num}.txt")
    issue_dst = os.path.join(workdir, "input_issue.md")
    if not os.path.exists(issue_dst):
        shutil.copyfile(issue_src, issue_dst)
    diff_text = None
    if os.path.exists(diff_src):
        with open(diff_src, encoding="utf-8") as f:
            diff_text = f.read()
        truncated = False
        if len(diff_text) > cfg["diff_max_chars"]:
            diff_text = diff_text[:cfg["diff_max_chars"]] + \
                "\n\n[ハーネス注記: 差分が上限を超えたため末尾を切り詰めた（先頭優先）]\n"
            truncated = True
        diff_dst = os.path.join(workdir, "input_diff.txt")
        if not os.path.exists(diff_dst):
            with open(diff_dst, "w", encoding="utf-8") as f:
                f.write(diff_text)
        rec["input"] = {"issue_chars": os.path.getsize(issue_src),
                        "diff_chars": len(diff_text), "diff_truncated": truncated}
    else:
        rec["input"] = {"issue_chars": os.path.getsize(issue_src),
                        "diff_chars": 0, "diff_truncated": False, "has_diff": False}
    total_chars = rec["input"]["issue_chars"] + rec["input"]["diff_chars"]
    if total_chars > cfg["input_warn_chars"]:
        msg = f"入力サイズ {total_chars} chars が警告閾値 {cfg['input_warn_chars']} を超過"
        if msg not in rec["warnings"]:
            rec["warnings"].append(msg)
        print(f"    [warn] {msg}")
    save_state(state)

    # --- バグ判定（条件付きセクション「バグの発生タイミング」の要否）。
    # ラベル（type: bug 等）で決定的に判定し、writer 指示と検証で共有する
    with open(issue_dst, encoding="utf-8") as f:
        issue_head = f.read()
    lm = re.search(r"^\*\*ラベル\*\*:\s*(.+)$", issue_head, re.M)
    is_bug = bool(lm and "bug" in lm.group(1).lower())
    rec["is_bug"] = is_bug
    save_state(state)
    guidelines = load_guidelines(cfg)
    bug_section = cfg.get("bug_section", "バグの発生タイミング")

    translated_path = os.path.join(workdir, "translated.md")
    plan_path = os.path.join(workdir, "plan.md")
    draft_path = os.path.join(workdir, "draft.md")
    review_path = os.path.join(workdir, "review.json")
    final_path = os.path.join(workdir, "final.md")
    retries = cfg["format_retries"]

    # --- translator（planner の前段。未完の場合のみ）
    if not os.path.exists(translated_path):
        if not run_translator_step(cfg, state, num, workdir):
            reason = rec.get("translation", {}).get(
                "reason", "翻訳工程が完了しなかった")
            return fail_item(state, key, f"翻訳検証: {reason}")
        if rec["status"] == "pending":
            rec["status"] = "translated"
            save_state(state)
    elif "translation" not in rec:
        rec["translation"] = {"status": "done",
                              "note": "既存の translated.md を検出"}
        save_state(state)

    # --- planner（未完の場合のみ）
    if not (os.path.exists(plan_path) and rec["status"] not in ("pending",)):
        note = ""
        plan_ok = False
        for attempt in range(1, retries + 2):
            before = V.snapshot_dir(workdir)
            res = call_role(cfg, state, key, "planner",
                            planner_prompt(guidelines["summary"], note),
                            workdir, allow=READ_ONLY_ALLOW, deny=READ_ONLY_DENY,
                            attempt=attempt)
            after = V.snapshot_dir(workdir)
            nw_ok, nw = V.validate_no_writes(before, after, res.files_modified)
            rec.setdefault("validation", {})["no_write_planner"] = nw
            if not nw_ok:
                save_state(state)
                return fail_item(state, key, f"検証8: planner がファイルを変更した {nw}")
            if not res.ok:
                return fail_item(state, key, f"planner 呼び出し失敗: {res.error}")
            text, trimmed = clean_plan_text(res.text)
            ok, det = V.validate_plan(text)
            if ok:
                with open(plan_path, "w", encoding="utf-8") as f:
                    f.write(text)
                rec["validation"]["plan_contract"] = {"ok": True, "preamble_trimmed": trimmed}
                plan_ok = True
                break
            note = (f"\n\n注意：前回の出力は形式不適合でした（不足項目: "
                    f"{', '.join(det['missing_markers'])}）。"
                    "5項目すべてを番号つきでこの順序のとおりに出力してください。")
        if not plan_ok:
            return fail_item(state, key, "検証7: planner 出力が契約に合わない（リトライ後も）")
        rec["status"] = "planned"
        save_state(state)

    # --- writer
    if not (os.path.exists(draft_path) and rec["status"] in
            ("drafted", "reviewed", "fixed", "verified", "done")):
        note = ""
        draft_ok = False
        for attempt in range(1, retries + 2):
            if os.path.exists(draft_path):
                os.remove(draft_path)
            res = call_role(
                cfg, state, key, "writer",
                writer_prompt(num, cfg["summary_template_sections"],
                              guidelines["summary"], bug_section, is_bug,
                              note),
                workdir,
                allow=("read", f"write({draft_path})"), deny=("shell",),
                attempt=attempt)
            if not res.ok:
                return fail_item(state, key, f"writer 呼び出し失敗: {res.error}")
            if not os.path.exists(draft_path):
                note = "\n\n注意：前回は draft.md が作成されませんでした。write ツールで draft.md を作成してください。"
                continue
            with open(draft_path, encoding="utf-8") as f:
                draft = f.read()
            # AI明示が混入していたら除去し、本文は最初の ## 見出しからにそろえる
            cleaned = V.strip_attributions(draft)
            guarded, applied = V.apply_preamble_guard(cleaned)
            if guarded != draft:
                with open(draft_path, "w", encoding="utf-8") as f:
                    f.write(guarded)
                draft = guarded
            if applied:
                rec["validation"]["preamble_guard_draft"] = True
            ok, det = V.validate_summary(draft, cfg["required_sections"],
                                         bug=is_bug, bug_section=bug_section)
            if ok:
                draft_ok = True
                break
            errs = det.get("errors") or [det.get("error", "不明な理由")]
            note = (f"\n\n注意：前回の draft.md は検証に合格しませんでした"
                    f"（{'; '.join(errs)}）。"
                    "構成を厳密に守って draft.md を作り直してください。")
        if not draft_ok:
            return fail_item(state, key, "検証2: writer 成果物が契約に合わない（リトライ後も）")
        rec["status"] = "drafted"
        save_state(state)

    # --- reviewer
    if not (os.path.exists(review_path) and rec["status"] in
            ("reviewed", "fixed", "verified", "done")):
        note = ""
        review_obj = None
        for attempt in range(1, retries + 2):
            before = V.snapshot_dir(workdir)
            res = call_role(cfg, state, key, "reviewer",
                            reviewer_prompt(guidelines["review"], note),
                            workdir, allow=READ_ONLY_ALLOW, deny=READ_ONLY_DENY,
                            attempt=attempt)
            after = V.snapshot_dir(workdir)
            nw_ok, nw = V.validate_no_writes(before, after, res.files_modified)
            rec.setdefault("validation", {})["no_write_reviewer"] = nw
            if not nw_ok:
                save_state(state)
                return fail_item(state, key, f"検証8: reviewer がファイルを変更した {nw}")
            if not res.ok:
                return fail_item(state, key, f"reviewer 呼び出し失敗: {res.error}")
            ok, det = V.validate_review(res.text)
            if ok:
                review_obj = det["review"]
                break
            note = ("\n\n注意：前回の出力は JSON として解釈できませんでした"
                    "（またはスキーマ不適合）。JSON のみを返してください。")
        if review_obj is None:
            return fail_item(state, key, "検証1: reviewer 出力が JSON スキーマに合わない（リトライ後も）")
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(review_obj, f, ensure_ascii=False, indent=2)
        rec["verdict_raw"] = review_obj["verdict"]
        rec["review_issues"] = len(review_obj.get("issues", []))
        # 正規化：issues が残っているのに pass の場合は、指摘を捨てず
        # revise として fixer に回す（reviewer 自身の判定は verdict_raw に保持）
        if review_obj["verdict"] == "pass" and rec["review_issues"] > 0:
            rec["verdict"] = "revise"
            rec["warnings"].append(
                "reviewer が pass と判定したが issues があったため revise に正規化")
        else:
            rec["verdict"] = review_obj["verdict"]
        rec["status"] = "reviewed"
        save_state(state)

    # --- fixer（revise のときだけ）
    if rec.get("verdict") == "revise" and not os.path.exists(final_path):
        note = ""
        fixed = False
        for attempt in range(1, retries + 2):
            res = call_role(cfg, state, key, "fixer", fixer_prompt(note),
                            workdir,
                            allow=("read", f"write({final_path})"), deny=("shell",),
                            attempt=attempt)
            if not res.ok:
                return fail_item(state, key, f"fixer 呼び出し失敗: {res.error}")
            if os.path.exists(final_path):
                fixed = True
                break
            note = ("\n\n注意：前回は final.md が作成されませんでした。"
                    "review.json の issues の範囲だけを修正し、final.md を作成してください。")
        if not fixed:
            return fail_item(state, key, "fixer が final.md を作成しなかった（リトライ後も）")
        rec["status"] = "fixed"
        save_state(state)
    elif rec.get("verdict") == "pass" and not os.path.exists(final_path):
        shutil.copyfile(draft_path, final_path)

    # --- verified（決定的検証の一括実行）
    # 最終成果物への決定的後処理（Claude 側と同じ分担で冪等に適用する）：
    # 混入した AI明示を除去 → 見出し前ガード → #参照リンク化（フェンス外のみ）
    # → AI明示を冒頭にちょうど1行付与
    with open(final_path, encoding="utf-8") as f:
        final_raw = f.read()
    body = V.strip_attributions(final_raw)
    body, applied = V.apply_preamble_guard(body)
    fetch_cfg = cfg.get("fetch", {})
    body = V.linkify(body, fetch_cfg.get("owner", ""),
                     fetch_cfg.get("repo", ""))
    final_text = (V.attribution_line(cfg["model"], "summary", date.today())
                  + "\n\n" + body.strip("\n") + "\n")
    if final_text != final_raw:
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(final_text)
    rec["summary_postprocess"] = {"attribution": True, "linkify": True,
                                  "preamble_guard": applied}
    with open(draft_path, encoding="utf-8") as f:
        draft_text = f.read()
    with open(review_path, encoding="utf-8") as f:
        review_text = f.read()
    with open(plan_path, encoding="utf-8") as f:
        plan_text = f.read()

    checks = {}
    ok1, _ = V.validate_review(review_text)
    checks["review_schema"] = ok1
    ok2, det2 = V.validate_summary(final_text, cfg["required_sections"],
                                   bug=is_bug, bug_section=bug_section)
    checks["summary_sections"] = {"ok": ok2, **det2}
    a_ok, a_det = V.validate_attribution(final_text, "summary")
    checks["attribution"] = {"ok": a_ok, **a_det}
    checks["preamble_guard_final"] = applied
    checks["diff_stats"] = V.diff_stats(draft_text, body,
                                        cfg["diff_change_warn_ratio"])
    ok5, det5 = V.validate_identifiers(final_text, diff_text)
    checks["identifiers"] = {"ok": ok5, **det5}
    item_log_total = round(log_item_credits(key), 4)
    checks["credits_consistent"] = V.credits_consistent(
        rec["credits_total"], item_log_total)
    checks["credits_state"] = rec["credits_total"]
    checks["credits_log"] = item_log_total
    ok7, _ = V.validate_plan(plan_text)
    checks["plan_contract"] = ok7
    rec["validation"].update(checks)
    save_state(state)

    failures = []
    if not ok1:
        failures.append("検証1: review.json スキーマ不適合")
    if not ok2:
        failures.append(f"検証2: 成果物のセクション不適合 {det2}")
    if not a_ok:
        failures.append(f"AI明示: 冒頭にちょうど1つでない {a_det}")
    if not ok5:
        failures.append(f"検証5: 識別子チェック不適合 {det5}")
    if not checks["credits_consistent"]:
        failures.append("検証6: クレジット集計が state と run-log で不一致")
    if not ok7:
        failures.append("検証7: plan.md が契約に合わない")
    if checks["diff_stats"]["warning"]:
        rec["warnings"].append(
            f"検証4: draft→final の変更比率 {checks['diff_stats']['change_ratio']} が大きい")
    if failures:
        return fail_item(state, key, "; ".join(failures))

    rec["status"] = "done"
    rec["finished"] = now_iso()
    save_state(state)
    print(f"    -> done (verdict={rec.get('verdict')}, "
          f"issues={rec.get('review_issues')}, credits={rec['credits_total']:.2f})")


# ---------------------------------------------------------------- preflight / backfill
def run_preflight(cfg) -> bool:
    """最小の実呼び出しでログイン疎通を確認する。消費は run-log に残す。"""
    pf_dir = os.path.join(RUNS_DIR, "_preflight")
    os.makedirs(pf_dir, exist_ok=True)
    print("事前確認（最小の実呼び出し）...")
    pf = run_copilot(cfg["copilot_bin"], "Reply with exactly the word: OK",
                     pf_dir, model=cfg["model"],
                     timeout=cfg["call_timeout_sec"],
                     raw_log_path=os.path.join(pf_dir, "stdout-preflight.jsonl"))
    append_log({"ts": now_iso(), "item": "preflight", "role": "preflight",
                "attempt": 1, "model": cfg["model"],
                "credits": round(pf.credits, 4), "tokens": pf.tokens,
                "seconds": pf.seconds, "ok": pf.ok,
                "exit_code": pf.exit_code, "error": pf.error or None})
    if not pf.ok:
        print(f"事前確認に失敗しました。本実行に入りません: {pf.error}")
        return False
    print(f"事前確認 OK (credits={pf.credits:.2f})")
    return True


def backfill_translate(cfg, state, args) -> int:
    """既存の件に翻訳だけを補完する。要約工程は再実行しない。

    対象は translated.md がまだ無い件。件の status は変更しない
    （done のまま）。成否は rec["translation"] に記録する。
    予算ガードは run-log 全体の累積ではなく「この補完実行の累積」
    （開始時点を baseline とした差分）に warn/stop を適用する。
    """
    targets = []
    for key in sorted(state["items"], key=int):
        wd = os.path.join(RUNS_DIR, f"issue_{key}")
        if not os.path.exists(os.path.join(wd, "translated.md")):
            targets.append(int(key))
    if args.items:
        wanted = {int(x) for x in args.items.split(",")}
        targets = [n for n in targets if n in wanted]
    if args.limit:
        targets = targets[:args.limit]
    print(f"翻訳補完の対象 {len(targets)} 件: {targets}")
    if not targets:
        return 0
    baseline = log_total_credits()
    if not run_preflight(cfg):
        return 2
    warned = False
    done_n = failed_n = 0
    for i, num in enumerate(targets, 1):
        session = log_total_credits() - baseline
        if session >= cfg["budget_stop_credits"]:
            print(f"予算ガード STOP: 補完実行の累積 {session:.2f} credits が"
                  f"停止ライン {cfg['budget_stop_credits']} に達したため停止します。")
            break
        if session >= cfg["budget_warn_credits"] and not warned:
            warned = True
            print(f"予算ガード WARN: 補完実行の累積 {session:.2f} credits が"
                  f"警告ライン {cfg['budget_warn_credits']} を超えました。続行します。")
        print(f"[{i}/{len(targets)}] issue #{num} 翻訳補完 "
              f"(補完実行の累積 {session:.2f} credits)")
        wd = os.path.join(RUNS_DIR, f"issue_{num}")
        try:
            ok = run_translator_step(cfg, state, num, wd)
        except FatalRun as e:
            print(f"致命的エラーにより停止します: {e}")
            save_state(state)
            return 2
        if ok:
            done_n += 1
        else:
            failed_n += 1
            print(f"    !! 翻訳が完了しませんでした（理由は state の "
                  f"translation に記録）")
    session = log_total_credits() - baseline
    print(f"翻訳補完 終了: 成功 {done_n} 件 / 失敗 {failed_n} 件 / "
          f"補完実行の消費 {session:.2f} credits")
    return 0


def retranslate_titles(cfg, state, args) -> int:
    """タイトル（先頭の見出し）が未訳の件だけ translator を再実行する。

    対象は translated.md が存在し、タイトルチェック（原文と同一 かつ
    日本語なし）に引っかかる件。要約工程は再実行しない。件の status は
    変更しない。失敗した場合は従前の translated.md を復元する。
    予算ガードは backfill と同じく「この再実行の累積」（baseline 差分）に
    warn/stop を適用する。
    """
    targets = []
    for key in sorted(state["items"], key=int):
        wd = os.path.join(RUNS_DIR, f"issue_{key}")
        tp = os.path.join(wd, "translated.md")
        ip = os.path.join(wd, "input_issue.md")
        if not (os.path.exists(tp) and os.path.exists(ip)):
            continue
        with open(ip, encoding="utf-8") as f:
            original = f.read()
        with open(tp, encoding="utf-8") as f:
            translated = f.read()
        if V.title_untranslated(original, translated):
            targets.append(int(key))
    if args.items:
        wanted = {int(x) for x in args.items.split(",")}
        targets = [n for n in targets if n in wanted]
    if args.limit:
        targets = targets[:args.limit]
    print(f"タイトル再翻訳の対象 {len(targets)} 件: {targets}")
    if not targets:
        return 0
    baseline = log_total_credits()
    if not run_preflight(cfg):
        return 2
    warned = False
    done_n = failed_n = 0
    for i, num in enumerate(targets, 1):
        session = log_total_credits() - baseline
        if session >= cfg["budget_stop_credits"]:
            print(f"予算ガード STOP: 再実行の累積 {session:.2f} credits が"
                  f"停止ライン {cfg['budget_stop_credits']} に達したため停止します。")
            break
        if session >= cfg["budget_warn_credits"] and not warned:
            warned = True
            print(f"予算ガード WARN: 再実行の累積 {session:.2f} credits が"
                  f"警告ライン {cfg['budget_warn_credits']} を超えました。続行します。")
        print(f"[{i}/{len(targets)}] issue #{num} タイトル再翻訳 "
              f"(再実行の累積 {session:.2f} credits)")
        wd = os.path.join(RUNS_DIR, f"issue_{num}")
        tp = os.path.join(wd, "translated.md")
        bak = tp + ".pre-titlefix.bak"
        shutil.copyfile(tp, bak)
        try:
            ok = run_translator_step(cfg, state, num, wd)
        except FatalRun as e:
            print(f"致命的エラーにより停止します: {e}")
            shutil.copyfile(bak, tp)
            os.remove(bak)
            save_state(state)
            return 2
        if ok:
            os.remove(bak)
            done_n += 1
        else:
            shutil.copyfile(bak, tp)
            os.remove(bak)
            rec = state["items"][str(num)]
            rec["translation"] = {
                "status": "done",
                "note": "タイトル再翻訳が検証に合格しなかったため、"
                        "従前の translated.md を復元した",
            }
            save_state(state)
            failed_n += 1
            print("    !! 再翻訳が完了しなかったため従前の翻訳を復元しました"
                  "（詳細は run-log を参照）")
    session = log_total_credits() - baseline
    print(f"タイトル再翻訳 終了: 成功 {done_n} 件 / 失敗 {failed_n} 件 / "
          f"再実行の消費 {session:.2f} credits")
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    global RUNS_DIR, STATE_PATH, LOG_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--items", type=str, default=None)
    ap.add_argument("--reset-failed", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--runs-dir", type=str, default=None,
                    help="状態一式の置き場所（既定 runs）")
    ap.add_argument("--fetch-only", action="store_true",
                    help="GitHub からの取得だけを行って終了する")
    ap.add_argument("--force-fetch", action="store_true",
                    help="取得済みの件も取り直す")
    ap.add_argument("--fetch-numbers", type=str, default=None,
                    help="取得する issue 番号（カンマ区切り。exclude を適用しない）")
    ap.add_argument("--backfill-translate", action="store_true",
                    help="既存の件に翻訳だけを補完する")
    ap.add_argument("--retranslate-titles", action="store_true",
                    help="タイトルが未訳の件だけ翻訳を再実行する")
    args = ap.parse_args()

    cfg = load_config()
    if args.runs_dir:
        RUNS_DIR = os.path.join(HERE, args.runs_dir)
        STATE_PATH = os.path.join(RUNS_DIR, "state.json")
        LOG_PATH = os.path.join(RUNS_DIR, "run-log.jsonl")
    os.makedirs(RUNS_DIR, exist_ok=True)

    if args.fetch_only:
        numbers = ([int(x) for x in args.fetch_numbers.split(",")]
                   if args.fetch_numbers else None)
        res = fetcher.fetch_missing(cfg, force=args.force_fetch,
                                    numbers=numbers)
        print(f"取得のみ実行: 対象 {len(res['targets'])} 件 / "
              f"取得 {len(res['fetched'])} 件 {res['fetched']} / "
              f"スキップ（取得済み） {len(res['skipped'])} 件 / "
              f"エラー {len(res['errors'])} 件 {res['errors']}")
        print(f"保存先: {res['dir']}")
        return 2 if res["errors"] else 0

    state = load_state(cfg)

    if not args.status:
        try:
            load_guidelines(cfg)
        except OSError as e:
            print(f"ガイドライン正本を読み込めません: {e}")
            return 2

    if args.backfill_translate:
        return backfill_translate(cfg, state, args)

    if args.retranslate_titles:
        return retranslate_titles(cfg, state, args)

    # 自前取得モード（input_base 未指定）では、処理前に未取得分を取得する
    # （--status は表示だけなので取得しない）
    if (not args.status and not cfg.get("input_base")
            and cfg.get("fetch", {}).get("enabled")):
        numbers = ([int(x) for x in args.items.split(",")]
                   if args.items else None)
        res = fetcher.fetch_missing(cfg, force=args.force_fetch,
                                    numbers=numbers)
        print(f"取得: 対象 {len(res['targets'])} 件 / 取得 {len(res['fetched'])} 件 / "
              f"スキップ {len(res['skipped'])} 件 / エラー {len(res['errors'])} 件")
        if res["errors"]:
            print(f"取得でエラーが発生したため停止します: {res['errors']}")
            return 2

    all_items = discover_items(cfg)

    if args.status:
        counts = {}
        for n in all_items:
            st = state["items"].get(str(n), {}).get("status", "pending")
            counts[st] = counts.get(st, 0) + 1
        print(f"対象 {len(all_items)} 件: {counts}")
        print(f"累積クレジット (run-log): {log_total_credits():.2f}")
        return 0

    if args.reset_failed:
        for key, rec in state["items"].items():
            if rec.get("status") == "failed":
                wd = os.path.join(RUNS_DIR, f"issue_{key}")
                if os.path.exists(os.path.join(wd, "review.json")):
                    rec["status"] = "reviewed"
                elif os.path.exists(os.path.join(wd, "draft.md")):
                    rec["status"] = "drafted"
                elif os.path.exists(os.path.join(wd, "plan.md")):
                    rec["status"] = "planned"
                elif os.path.exists(os.path.join(wd, "translated.md")):
                    rec["status"] = "translated"
                else:
                    rec["status"] = "pending"
                rec["failure"] = None
        save_state(state)

    targets = all_items
    if args.items:
        targets = [int(x) for x in args.items.split(",")]
    todo = []
    for n in targets:
        st = state["items"].get(str(n), {}).get("status", "pending")
        if st == "done":
            continue
        if st == "failed":
            print(f"#{n}: failed のためスキップ（--reset-failed で再実行可）")
            continue
        todo.append(n)
    if args.limit:
        todo = todo[:args.limit]

    done_count = sum(1 for n in all_items
                     if state["items"].get(str(n), {}).get("status") == "done")
    print(f"対象 {len(all_items)} 件 / 完了済み {done_count} 件 / "
          f"今回の実行対象 {len(todo)} 件: {todo}")
    print(f"開始時点の累積クレジット: {log_total_credits():.2f} "
          f"(warn {cfg['budget_warn_credits']} / stop {cfg['budget_stop_credits']})")
    if not todo:
        return 0

    # --- 事前確認：最小の実呼び出しで疎通を確認する
    if not run_preflight(cfg):
        return 2

    if log_total_credits() >= cfg["budget_stop_credits"]:
        print("予算ガード: 累積が stop ラインに達しているため開始しません。")
        return 3

    for i, num in enumerate(todo, 1):
        total = log_total_credits()
        if total >= cfg["budget_stop_credits"]:
            print(f"予算ガード STOP: 累積 {total:.2f} credits が停止ライン "
                  f"{cfg['budget_stop_credits']} に達したため、新規の件に入らず停止します。")
            return 3
        if total >= cfg["budget_warn_credits"] and not state.get("budget_warned"):
            state["budget_warned"] = True
            save_state(state)
            print(f"予算ガード WARN: 累積 {total:.2f} credits が警告ライン "
                  f"{cfg['budget_warn_credits']} を超えました。続行します。")
        print(f"[{i}/{len(todo)}] issue #{num} "
              f"(累積 {total:.2f} credits)")
        try:
            process_item(cfg, state, num)
        except FatalRun as e:
            print(f"致命的エラーにより停止します: {e}")
            save_state(state)
            return 2
        except KeyboardInterrupt:
            save_state(state)
            print("中断されました。状態は保存済みです。")
            return 130

    total = log_total_credits()
    counts = {}
    for n in all_items:
        st = state["items"].get(str(n), {}).get("status", "pending")
        counts[st] = counts.get(st, 0) + 1
    print(f"終了: 状態 {counts} / 累積クレジット {total:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
