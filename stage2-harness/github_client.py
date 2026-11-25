"""GitHub API クライアント（第2段階ハーネス同梱・標準ライブラリのみ）。

認証は2経路ある。

1. 本線：環境変数 GITHUB_TOKEN（Personal Access Token）を
   Authorization: Bearer ヘッダで送る。これだけで自己完結する。
2. フォールバック：GITHUB_TOKEN が未設定の場合のみ、この Muse 環境の
   custom.github コネクタ（dynamic_credentials サロゲート）経由にする。
   これは Muse 環境専用の経路で、他の環境では使えない（その場合は
   GITHUB_TOKEN を設定すること）。サロゲートは api.github.com への
   リクエスト時にだけ差し込まれ、トークンの実値はこのコードにも
   ログにも現れない。

挙動（エンドポイント、ヘッダ、レート制限時の待機・再試行、ページング、
closing 参照の選定、normalize の整形）は、検証済みの従来実装と等価に
そろえてある。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
CONNECTOR = "custom.github"
ALLOWED_HOSTS = ["api.github.com"]
_DC_DIR = "/opt/muse/skills/custom-connector-setup/bin"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


class _Resp:
    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = headers
        self._body = body

    def json(self):
        return json.loads(self._body.decode("utf-8"))

    @property
    def text(self):
        return self._body.decode("utf-8", "replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"GitHub API error {self.status_code}: {self.text[:300]}")


def _attach_auth(req) -> None:
    """リクエストに認証を付ける。トークンの実値はログに出さない。"""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        return
    # フォールバック（Muse 環境専用）：custom.github コネクタ経由。
    try:
        if _DC_DIR not in sys.path:
            sys.path.insert(0, _DC_DIR)
        from dynamic_credentials import add_surrogate_to_request
    except Exception as e:
        raise RuntimeError(
            "GITHUB_TOKEN が未設定で、フォールバック用の "
            "dynamic_credentials（Muse 環境専用）も利用できません。"
            "GITHUB_TOKEN を設定してください。") from e
    add_surrogate_to_request(req, CONNECTOR, allowed_hosts=ALLOWED_HOSTS)


class GitHubClient:
    def __init__(self, owner, repo):
        self.owner = owner
        self.repo = repo
        self.base = f"{GITHUB_API}/repos/{self.owner}/{self.repo}"

    # ---- 基本取得 ----
    def _get(self, url, params=None, accept=None):
        """レート制限（403 + X-RateLimit-Remaining: 0）時はリセットまで待って再試行。"""
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        resp = None
        for attempt in range(3):
            req = urllib.request.Request(url)
            req.add_header("Accept", accept or "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            req.add_header("User-Agent", "github-issue-translate")
            _attach_auth(req)
            opener = urllib.request.build_opener(NoRedirect())
            try:
                with opener.open(req, timeout=60) as r:
                    resp = _Resp(r.status, r.headers, r.read())
            except urllib.error.HTTPError as e:
                resp = _Resp(e.code, e.headers, e.read())
            if (resp.status_code == 403
                    and resp.headers.get("X-RateLimit-Remaining") == "0"):
                reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                wait = max(5, min(reset - int(time.time()) + 5, 3700))
                print(f"rate limit: {wait}秒待機して再試行します ({url})",
                      flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def get_issue(self, number):
        return self._get(f"{self.base}/issues/{number}").json()

    def milestone_number(self, title):
        page = 1
        while True:
            items = self._get(
                f"{self.base}/milestones",
                params={"state": "all", "per_page": 100, "page": page}).json()
            if not items:
                return None
            for m in items:
                if m["title"] == title:
                    return m["number"]
            page += 1

    def list_issues(self, state="open", milestone="*", labels=None,
                    max_issues=100, order="desc"):
        params = {"state": state, "per_page": 100, "sort": "created",
                  "direction": order}
        if milestone == "none":
            params["milestone"] = "none"
        elif milestone and milestone != "*":
            num = self.milestone_number(milestone)
            if num is None:
                raise ValueError(f"マイルストーンが見つかりません: {milestone}")
            params["milestone"] = num
        if labels:
            params["labels"] = ",".join(labels)
        out, page = [], 1
        while len(out) < max_issues:
            params["page"] = page
            items = self._get(f"{self.base}/issues", params=params).json()
            if not items:
                break
            for it in items:
                if "pull_request" in it:
                    continue
                out.append(it)
                if len(out) >= max_issues:
                    break
            page += 1
        return out

    def get_comments(self, number, max_comments=20):
        items = self._get(f"{self.base}/issues/{number}/comments",
                          params={"per_page": 100}).json()
        return items[:max_comments]

    # ---- Diff取得 ----
    def get_timeline(self, number):
        events, page = [], 1
        while True:
            items = self._get(f"{self.base}/issues/{number}/timeline",
                              params={"per_page": 100, "page": page}).json()
            if not items:
                break
            events.extend(items)
            page += 1
        return events

    def find_closing_reference(self, number):
        events = self.get_timeline(number)
        refs = []
        for ev in events:
            et = ev.get("event")
            if et == "cross-referenced":
                src = (ev.get("source") or {}).get("issue") or {}
                if "pull_request" in src:
                    refs.append({"type": "pr", "number": src["number"],
                                 "created_at": ev.get("created_at", "")})
            elif et in ("closed", "referenced") and ev.get("commit_id"):
                refs.append({"type": "commit", "sha": ev["commit_id"],
                             "created_at": ev.get("created_at", "")})
        if not refs:
            return None
        refs.sort(key=lambda r: r["created_at"])
        latest = refs[-1]
        prs = [r for r in refs if r["type"] == "pr"]
        if prs:
            latest = prs[-1]
        return latest

    def get_pr_diff(self, number, max_size):
        r = self._get(f"{self.base}/pulls/{number}",
                      accept="application/vnd.github.v3.diff")
        return r.text, f"https://github.com/{self.owner}/{self.repo}/pull/{number}"

    def get_commit_diff(self, sha, max_size):
        r = self._get(f"{self.base}/commits/{sha}",
                      accept="application/vnd.github.v3.diff")
        return r.text, f"https://github.com/{self.owner}/{self.repo}/commit/{sha}"


def normalize_issue(raw, comments, closing_reference):
    """APIレスポンスを従来スキーマに整形する（従来実装と同一）。"""
    return {
        "number": raw["number"],
        "title": raw["title"],
        "state": raw["state"],
        "author": raw["user"]["login"],
        "created_at": raw["created_at"],
        "updated_at": raw["updated_at"],
        "url": raw["html_url"],
        "labels": [l["name"] for l in raw.get("labels", [])],
        "body": raw.get("body") or "",
        "milestone": (raw.get("milestone") or {}).get("title"),
        "comments": [
            {"author": c["user"]["login"], "created_at": c["created_at"],
             "body": c.get("body") or ""}
            for c in comments
        ],
        "closing_references": closing_reference,
    }
