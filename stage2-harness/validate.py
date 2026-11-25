"""決定的検証（第2段階ハーネス）。

設計書第6章の8項目を、モデルに任せずコードで担保する。
各関数は (ok: bool, details: dict) を返す。details には理由・警告・
ガード適用の記録など、state.json に残すべき情報を入れる。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re

PLAN_MARKERS = ["要件の要約", "前提と未確認点", "影響範囲", "実装手順", "検証方法"]
SEVERITIES = ("must", "should", "nit")


# --- 検証7: planner 出力が出力契約（5項目構成）に合っていること -------------
def validate_plan(text: str) -> tuple[bool, dict]:
    missing = [m for m in PLAN_MARKERS if m not in text]
    return (not missing), {"missing_markers": missing}


# --- 検証1: review.json のスキーマ -------------------------------------------
def extract_json(text: str) -> dict | None:
    """応答テキストから JSON オブジェクトを取り出す。

    素の JSON が基本。コードフェンスや前後の文章が混ざった場合は
    最初の { から最後の } までをフォールバックとして抽出する。
    """
    t = text.strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(t[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def validate_review(text: str) -> tuple[bool, dict]:
    obj = extract_json(text)
    if obj is None:
        return False, {"error": "JSONとしてパースできない"}
    errors = []
    verdict = obj.get("verdict")
    if verdict not in ("pass", "revise"):
        errors.append(f"verdict が不正: {verdict!r}")
    issues = obj.get("issues")
    if not isinstance(issues, list):
        errors.append("issues が配列でない")
        issues = []
    else:
        for i, it in enumerate(issues):
            if not isinstance(it, dict):
                errors.append(f"issues[{i}] がオブジェクトでない")
                continue
            if it.get("severity") not in SEVERITIES:
                errors.append(f"issues[{i}].severity が値域外: {it.get('severity')!r}")
            for key in ("location", "reason", "fix"):
                if not isinstance(it.get(key), str) or not it[key].strip():
                    errors.append(f"issues[{i}].{key} が空または文字列でない")
    details = {"review": obj, "errors": errors}
    if verdict == "pass" and issues:
        # スキーマ違反ではない。verdict の解釈（issues があれば revise として
        # 扱う正規化）はハーネス側で行う（設計書第6章の検証1はスキーマ適合まで）
        details["note"] = "verdict=pass だが issues あり（ハーネス側で revise に正規化）"
    return (not errors), details


# --- 後処理（決定的変換）: AI明示の付与・除去と #参照のリンク化 --------------
# Claude 側パイプライン（github_issue_translate）と方式をそろえる。
# AI明示はモデルに書かせず、ハーネスが後処理でちょうど1行だけ付与する。
# リンク化もモデル任せにせず、コードフェンス外だけを決定的に変換する。

_ATTR_GENERIC_RE = re.compile(
    r"^\s*\*（?このドキュメントは生成AI\(.+\)によって"
    r"\d{4}年\d{1,2}月\d{1,2}日に生成されました）?。?\*?\s*$")
_ATTR_STYLE_RES = {
    "translation": re.compile(
        r"^\*（このドキュメントは生成AI\(.+\)によって"
        r"\d{4}年\d{1,2}月\d{1,2}日に生成されました）\*$"),
    "summary": re.compile(
        r"^\*このドキュメントは生成AI\(.+\)によって"
        r"\d{4}年\d{1,2}月\d{1,2}日に生成されました。\*$"),
}


def pretty_model(model: str) -> str:
    """'claude-sonnet-5.5' -> 'Claude Sonnet 5.5'（Claude 側と同じ表記変換）。"""
    parts = model.split("-")
    words, nums = [], []
    for p in parts:
        (nums if p[0:1].isdigit() else words).append(p)
    name = " ".join(w.capitalize() for w in words)
    return f"{name} {'.'.join(nums)}" if nums else name


def attribution_model_display(model: str) -> str:
    """AI明示に書く生成主体。Copilot 側の実態（GitHub Copilot＋モデル名）。"""
    return f"GitHub Copilot / {pretty_model(model)}"


def attribution_line(model: str, style: str, d) -> str:
    """ガイドライン指定形式の AI明示行を1行作る。

    style="translation": *（このドキュメントは生成AI(...)によって...）*
    style="summary":     *このドキュメントは生成AI(...)によって...。*
    （様式の違いは Claude 側成果物の実形式に合わせたもの）
    """
    base = (f"このドキュメントは生成AI({attribution_model_display(model)})"
            f"によって{d.year}年{d.month}月{d.day}日に生成されました")
    if style == "translation":
        return f"*（{base}）*"
    return f"*{base}。*"


def strip_attributions(text: str) -> str:
    """AI明示行（モデルが混入させた分を含む）をすべて取り除く。

    明示はハーネスが後処理でちょうど1行だけ付与し直すため、検証や
    本文整形の前にこれで素の本文に戻す。
    """
    lines = [ln for ln in text.splitlines()
             if not _ATTR_GENERIC_RE.match(ln)]
    return "\n".join(lines).strip("\n") + ("\n" if lines else "")


def validate_attribution(text: str, style: str) -> tuple[bool, dict]:
    """AI明示が「冒頭にちょうど1つ」あることを確認する。"""
    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines) if _ATTR_GENERIC_RE.match(ln)]
    details = {"attribution_count": len(hits), "style": style}
    if len(hits) != 1:
        details["error"] = f"AI明示の数が {len(hits)}（ちょうど1つでない）"
        return False, details
    if hits[0] != 0:
        details["error"] = "AI明示が文書の先頭行にない"
        return False, details
    if not _ATTR_STYLE_RES[style].match(lines[0]):
        details["error"] = f"AI明示の形式が {style} 様式に合わない"
        return False, details
    details["line"] = lines[0]
    return True, details


_ISSUE_URL = "https://github.com/{owner}/{repo}/issues/{n}"


def linkify(text: str, owner: str, repo: str) -> str:
    """#XXXX をリンク形式に変換する（Claude 側 translate.py と同じ方式）。

    コードフェンス（```）内は対象外。あわせて、メタ情報の
    「**Issue番号**: #N」行は Claude 側成果物でもリンク化されていない
    ため対象外とする。
    """
    parts = text.split("```")
    for i in range(0, len(parts), 2):  # 偶数インデックスがフェンス外
        lines = parts[i].split("\n")
        for j, ln in enumerate(lines):
            if ln.startswith("**Issue番号**"):
                continue
            lines[j] = re.sub(
                r"(?<![\w/\[(])#(\d+)\b",
                lambda m: f"[#{m.group(1)}](" + _ISSUE_URL.format(
                    owner=owner, repo=repo, n=m.group(1)) + ")",
                ln)
        parts[i] = "\n".join(lines)
    return "```".join(parts)


# --- 検証3: 最初の見出しより前の混入を切り捨てるガード -----------------------
def apply_preamble_guard(text: str) -> tuple[str, bool]:
    """要約本文の前に混入した作業メモ等を取り除く。

    Claude 側 summarize.py の strip_preamble と同じ前提：要約本文は
    最初の「## 」見出しから始まる。それより前にある非空テキストを
    切り捨てる（AI明示行は先に strip_attributions で除去しておくこと）。

    戻り値: (整形後テキスト, ガードを適用したか)
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## "):
            head = [ln for ln in lines[:i]
                    if ln.strip() and ln.strip() != "---"]
            if head:
                return "\n".join(lines[i:]).strip() + "\n", True
            return text, False
    return text, False


# --- 検証2: 成果物が空でなく必須セクションがそろっていること -----------------
def validate_summary(text: str, required_sections: list[str],
                     bug: bool = False,
                     bug_section: str = "バグの発生タイミング"
                     ) -> tuple[bool, dict]:
    """要約の構成検証（ガイドラインの構成に合わせたもの）。

    - AI明示行とコードフェンス内は構造判定から除く
    - 必須セクション（課題概要／原因／対応方針）が順序どおりに存在すること
    - 先頭のタイトル行（H1）は付けない（Claude 側成果物の実形式）
    - バグ issue のときだけ、条件付きセクション（バグの発生タイミング）
      が必須になる。それ以外の issue では有無を問わない
    """
    body = strip_attributions(text)
    if not body.strip():
        return False, {"error": "成果物が空"}
    structural = _FENCE_RE.sub("", body)
    errors: list[str] = []
    has_h1 = bool(re.search(r"^#\s", structural, re.M))
    if has_h1:
        errors.append("タイトル行（H1）がある（要約は ## 課題概要 から始める）")
    positions: dict[str, int] = {}
    missing = []
    for s in required_sections:
        m = re.search(rf"^##\s*{re.escape(s)}\s*$", structural, re.M)
        if m:
            positions[s] = m.start()
        else:
            missing.append(s)
    if missing:
        errors.append(f"必須セクション欠落: {missing}")
    order_ok = True
    seq = [positions[s] for s in required_sections if s in positions]
    if seq != sorted(seq):
        order_ok = False
        errors.append("必須セクションの順序がガイドラインと異なる")
    has_bug_section = bool(
        re.search(rf"^##\s*{re.escape(bug_section)}\s*$", structural, re.M))
    if bug and not has_bug_section:
        errors.append(
            f"バグ issue なのに条件付きセクション「{bug_section}」がない")
    return (not errors), {
        "missing_sections": missing, "has_h1": has_h1,
        "section_order_ok": order_ok, "bug": bug,
        "has_bug_section": has_bug_section, "errors": errors}


# --- 検証5: 入力の識別子・変更ファイルが成果物に残っていること（簡易） --------
def changed_files(diff_text: str) -> list[str]:
    files = re.findall(r"^\+\+\+ b/(.+)$", diff_text, re.M)
    return [f for f in files if not f.endswith("/dev/null")]


def validate_identifiers(final_text: str, diff_text: str | None) -> tuple[bool, dict]:
    code_spans = re.findall(r"`[^`\n]+`", final_text)
    details: dict = {"code_spans": len(code_spans)}
    if diff_text is None:
        details["skipped"] = "diff が無い題材のためファイル名チェックは省略"
        return len(code_spans) > 0, details
    files = changed_files(diff_text)
    sources = [os.path.basename(f) for f in files
               if "/test" not in f.lower() and "Test" not in os.path.basename(f)]
    details["changed_source_files"] = sources
    # ファイル名そのものか、拡張子を除いたクラス名のどちらかが
    # 成果物に現れれば「変更対象が特定できる」とみなす
    mentioned = [s for s in sources
                 if s in final_text or os.path.splitext(s)[0] in final_text]
    details["mentioned"] = mentioned
    ok = len(code_spans) > 0 and (not sources or len(mentioned) > 0)
    if sources and not mentioned:
        details["error"] = "変更対象の主要ファイル名が成果物に一度も現れない"
    return ok, details


# --- 検証4: fixer の変更量の記録（範囲外の大幅な書き換えは警告） -------------
def diff_stats(before: str, after: str, warn_ratio: float) -> dict:
    a = before.splitlines()
    b = after.splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    base = max(len(a), 1)
    ratio = changed / base
    return {
        "draft_lines": len(a),
        "final_lines": len(b),
        "changed_lines": changed,
        "change_ratio": round(ratio, 3),
        "warning": ratio > warn_ratio,
    }


# --- 検証8: 読み取り専用役割がファイルを書いていないこと ----------------------
def snapshot_dir(path: str) -> dict[str, str]:
    snap = {}
    for name in sorted(os.listdir(path)):
        fp = os.path.join(path, name)
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                snap[name] = hashlib.sha256(f.read()).hexdigest()
    return snap


def validate_no_writes(before: dict, after: dict, files_modified: list) -> tuple[bool, dict]:
    changed = [n for n in set(before) | set(after)
               if before.get(n) != after.get(n)]
    ok = not changed and not files_modified
    return ok, {"changed_files": changed, "cli_files_modified": files_modified}


# --- 翻訳検証: コードブロック・見出し構造・欠落チェック -----------------------
_FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```\s*$", re.M | re.S)
_HEADING_RE = re.compile(r"^(#{1,6})\s", re.M)


def extract_code_blocks(text: str) -> list[str]:
    return _FENCE_RE.findall(text)


def heading_levels(text: str) -> list[int]:
    """コードブロック内を除いた見出しレベルの列を返す。"""
    stripped = _FENCE_RE.sub("", text)
    return [len(m.group(1)) for m in _HEADING_RE.finditer(stripped)]


_JP_RE = re.compile(r"[぀-ヿ一-鿿]")


def first_heading_text(text: str) -> str | None:
    """コードブロック内を除いた、最初の見出しのテキストを返す。"""
    stripped = _FENCE_RE.sub("", text)
    m = re.search(r"^#{1,6}\s+(.+?)\s*$", stripped, re.M)
    return m.group(1) if m else None


def title_untranslated(original: str, translated: str) -> bool:
    """タイトル（先頭の見出し）が未訳かどうか。

    判定は「原文と同一 かつ 日本語文字を含まない」に限定する
    （これ以外の条件で不合格にしたり、例外で合格にしたりしない）。
    """
    ot = first_heading_text(original)
    tt = first_heading_text(translated)
    if ot is None or tt is None:
        return False
    return tt == ot and not _JP_RE.search(tt)


def validate_translation(original: str, translated: str,
                         min_ratio: float = 0.35) -> tuple[bool, dict]:
    """翻訳の決定的検証。

    - 空でないこと
    - コードフェンスの数と中身が原文と完全一致すること
    - 見出しレベルの列（構造）が原文と一致すること
    - 文字数が原文に対して極端に短くないこと（明らかな欠落の検出）
    - タイトル（先頭の見出し）が未訳でないこと
      （原文と同一 かつ 日本語文字を含まない場合のみ不合格）
    """
    details: dict = {}
    errors: list[str] = []
    if not translated.strip():
        return False, {"error": "翻訳が空"}
    ob = extract_code_blocks(original)
    tb = extract_code_blocks(translated)
    details["code_blocks_original"] = len(ob)
    details["code_blocks_translated"] = len(tb)
    details["code_blocks_identical"] = ob == tb
    if ob != tb:
        errors.append(
            f"コードブロックが原文と一致しない (原文 {len(ob)} 件 / 翻訳 {len(tb)} 件)")
    oh = heading_levels(original)
    th = heading_levels(translated)
    details["headings_original"] = oh
    details["headings_translated"] = th
    if oh != th:
        errors.append(f"見出し構造が原文と異なる (原文 {oh} / 翻訳 {th})")
    ot = first_heading_text(original)
    tt = first_heading_text(translated)
    details["title_original"] = ot
    details["title_translated"] = tt
    details["title_identical_to_original"] = (ot is not None and tt == ot)
    details["title_has_japanese"] = bool(tt and _JP_RE.search(tt))
    if title_untranslated(original, translated):
        errors.append(
            "タイトル（先頭の見出し）が未訳（原文と同一で日本語を含まない）")
    details["title_has_backtick"] = bool(tt and "`" in tt)
    if tt and "`" in tt:
        # ガイドラインのタイトル翻訳ルール（バッククォートで囲まない）。
        # Claude 側成果物も全件バッククォートなしが実形式
        errors.append(
            "タイトル（先頭の見出し）にバッククォートが含まれている")
    ratio = len(translated) / max(len(original), 1)
    details["char_ratio"] = round(ratio, 3)
    details["original_chars"] = len(original)
    details["translated_chars"] = len(translated)
    if ratio < min_ratio:
        errors.append(
            f"翻訳の文字数比率 {ratio:.2f} が下限 {min_ratio} 未満（欠落の疑い）")
    details["errors"] = errors
    return (not errors), details


# --- 検証6: クレジット集計の一致 ----------------------------------------------
def credits_consistent(state_total: float, log_total: float, tol: float = 0.011) -> bool:
    return abs(state_total - log_total) <= tol
