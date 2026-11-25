# 第2段階ハーネス — 薄い自作ハーネス（Copilot CLI バッチ実行基盤）

設計書 `../stage2-harness-design.md` に基づく実装です。
**取得 → 翻訳 → 計画 → 執筆 → レビュー → 修正 → 検証** を Copilot で
一気通貫に回す基盤で、取得は GitHub API（認証済み経路）、以降の5役割
（translator → planner → writer → reviewer → fixer）は件ごとに新規
プロセス（`copilot -p --agent <役割> --model claude-sonnet-5.5
--output-format json`）で直列に回し、決定的検証（validate.py）を通った
件だけを成果物にします。

## ファイル

| ファイル | 役割 |
|---|---|
| `harness.py` | 進行役。対象リスト・状態復元・役割遷移・予算ガード |
| `fetcher.py` | GitHub からの issue 取得。既存パイプライン（github_issue_translate）の認証済みクライアントを import して再利用し、`inputs/` に保存する |
| `copilot_runner.py` | Copilot CLI 呼び出しと JSONL 解析（最終応答・credits・tokens の分離） |
| `validate.py` | 決定的検証8項目（JSONスキーマ、必須セクション、見出し前混入ガード、識別子、計画契約、権限逸脱ほか）＋翻訳検証＋後処理（AI明示・#参照リンク化） |
| `config.json` | モデル固定（claude-sonnet-5.5）、予算 warn 300 / stop 600、入力閾値、必須セクション、取得設定（`fetch`）、ガイドライン正本の場所（`guidelines_dir`）等 |
| `inputs/` | 自前取得の保存先（`<repo>/<milestone>/<state>/current/markdown/` に `issues/` と `issues_diff/`） |
| `runs/` | 実行状態と成果物（下記） |

## 実行状態と成果物（runs/）

- `runs/state.json` — 件ごとの状態・役割ごとの成否と usage・検証結果・失敗理由。
  更新は一時ファイル経由の原子的置き換え。中断しても壊れません。
- `runs/run-log.jsonl` — 呼び出し単位の追記型ログ（時刻・件・役割・credits・tokens・成否）。
  予算ガードの集計はこの実測値だけを使います。
- `runs/issue_<番号>/` — 件ごとの作業フォルダ。
  `input_issue.md` / `input_diff.txt`（入力のコピー）、`translated.md`（全文翻訳）、
  `plan.md`、`draft.md`、`review.json`、`final.md`（最終成果物）、
  `logs/stdout-<役割>.jsonl`（生の JSONL。
  ハーネス自身の書き込みを検証8が誤検出しないようサブフォルダに分離）。

## 使い方

```bash
cd stage2-harness
python3 harness.py --status     # 進捗と累積クレジットの確認（呼び出しなし）
python3 harness.py --limit 2    # 先頭2件だけ実行（小規模確認）
python3 harness.py              # 残件をすべて実行（必要なら取得から）
python3 harness.py --items 5158,5514   # 件を指定
python3 harness.py --fetch-only        # GitHub からの取得だけを行う
python3 harness.py --fetch-only --fetch-numbers 5158,5570  # 番号指定で取得
python3 harness.py --backfill-translate  # done 済みの件に翻訳だけ補完
python3 harness.py --runs-dir runs-e2e   # 状態一式を別フォルダで実行
```

## 取得工程（fetcher.py）

- 取得は既存パイプライン（`~/workspace/github_issue_translate`）の
  `github_client.py`（GitHubClient）と `fetch.py`（issue_markdown）を
  import して再利用します。認証は custom.github コネクタの
  dynamic_credentials サロゲート経由で、新しい認証情報は扱いません。
- 設定は `config.json` の `fetch` 節です：`owner` / `repo` / `milestone` /
  `state`（closed）/ `order`（asc/desc）/ `max_issues` / `issue_numbers`
  （null なら一覧から取得）/ `max_comments` / `max_diff_size`。
  対象の除外は従来どおりトップレベルの `exclude_issues` が唯一の指定場所で、
  取得・処理の両方に効きます。ただし番号を明示した場合
  （`fetch.issue_numbers` または `--fetch-numbers`）は明示指定を優先し、
  除外を適用しません。
- 保存先は `inputs/<repo>/<milestone>/<state>/current/markdown/` で、
  レイアウトは従来の input_base と同一です。既にファイルがある件は
  再取得しません（`--force-fetch` の明示指定でのみ取り直します）。
- 通常実行（自前取得モード）では、処理前に未取得分を自動で取得します。
  エラー（レート制限含む）が発生したら、その時点で中止して報告します。

### input_base の意味と移行方法

- `config.json` の `input_base` が **null**（現在の設定）：自前取得モード。
  入力は `inputs/` から読みます。
- `input_base` にフォルダパスを指定：従来モード。外部で取得済みの
  フォルダ（`issues/` と `issues_diff/` を含む場所）から読み、自動取得は
  行いません（`--fetch-only` で `inputs/` へ取得することは可能です）。
- 移行は `input_base` を null に戻すだけです。`inputs/` のレイアウトが
  従来と同一なので、対象リストや処理フローに変更は要りません。

## ガイドラインへの準拠

役割の基準は、ユーザーのガイドライン正本にそろえてあります
（Claude 側パイプライン github_issue_translate と同じ方式）。

- **正本は1か所**：`config.json` の `guidelines_dir`（既定は
  `~/workspace/github_issue_translate`）にある `TRANSLATION_GUIDELINE.md`／
  `SUMMARY_GUIDELINE.md`／`REVIEW_GUIDELINE.md`（ファイル名は
  `guideline_files` で変更可）。ハーネスは実行時に読み込み、各役割の
  プロンプトに全文を埋め込んで渡します。
- **分担**：translator は TRANSLATION_GUIDELINE、planner／writer は
  SUMMARY_GUIDELINE が基準です。reviewer は REVIEW_GUIDELINE を渡した
  うえで、プロンプト冒頭で立脚点を「想定読者ペルソナ（Spring Batch を
  業務で2〜3年使う中堅エンジニア）として読んだときのチェック」と明示し、
  観点の優先順位（難しさ・堅苦しさ・業務への効き方を中心に、形式ルールは
  その次）を伝えます。fixer は従来どおり reviewer の JSON 指示の範囲だけ
  を直します。
- **優先順位**：ガイドライン内の出力先・ファイル名・パラメータ等の記述と
  ハーネスの実行契約が衝突する場合は、ハーネス側の契約が優先する旨を
  各プロンプトで明示しています（reviewer の JSON スキーマもハーネスの
  現行契約を維持）。
- **要約の構成**：必須セクションは「課題概要／原因／対応方針」
  （`required_sections`）。「バグの発生タイミング」（`bug_section`）は
  バグ issue（ラベルに bug を含む件）だけの条件付き必須セクションとして、
  writer への指示と検証の両方に反映しています。要約にタイトル行（H1）は
  付けず、`## 課題概要` から始めます（Claude 側成果物の実形式）。
- **AI明示**：翻訳・要約の冒頭に、ガイドライン指定形式の明示を
  ちょうど1行だけ入れます。生成主体は Copilot 側の実態
  （`GitHub Copilot / <モデル名>`）とし、様式は Claude 側成果物に合わせ
  翻訳は `*（...）*`、要約は `*...。*` です。モデルには書かせず、
  ハーネスの決定的後処理で付与し、検証で「冒頭にちょうど1つ」を
  確認します。
- **#参照のリンク化**：Claude 側と同じ決定的後処理を翻訳・要約の
  成果物に適用します（コードフェンス外のみ変換。リンク先は `fetch`
  設定の owner/repo から組み立て）。メタ情報の「**Issue番号**: #N」行は
  Claude 側成果物でもリンク化されていないため対象外です。コード
  フェンス内は変換しないので、翻訳検証のコードブロック完全一致と
  矛盾しません。
- **タイトル**：翻訳タイトルは日本語化し、バッククォートで囲まない
  （ガイドラインのタイトル翻訳ルール。検証でもチェックします）。

## 翻訳工程（translator）

- 状態遷移は `pending → translated → planned → drafted → reviewed →
  (fixed) → verified → done` です。translator は planner の前段で
  `input_issue.md` の本文・コメントを全文翻訳し、`translated.md` を作ります。
- 翻訳の決定的検証（validate.py の `validate_translation`）：
  コードフェンスの数と中身が原文と完全一致すること／見出しレベルの列
  （構造）が原文と一致すること／空でないこと／文字数比率が下限
  （`translation_min_ratio`、既定 0.35）以上であること／タイトルが
  未訳でないこと／タイトルにバッククォートが含まれないこと。
  不合格は理由つきで記録し、形式不適合のリトライは1回まで（他役割と同方針）。
  検証を通った翻訳には、後処理で #参照リンク化と AI明示の付与を行って
  から保存します。
- 既存の done 済みの件への補完は `--backfill-translate` を使います。
  要約工程は再実行せず、件の status も done のまま変えません。成否は
  state の `translation` に、消費は通常の役割記録（roles.translator）と
  run-log に残ります。予算ガードは run-log 全体の累積ではなく
  「補完実行の累積」（開始時点との差分）に warn 300 / stop 600 を適用します。

- 実行前には最小の実呼び出し（preflight）でログイン疎通を確認します。
  失敗したら本実行に入りません。
- 認証エラー・レート制限が出たら粘らず停止します（状態は保存済み）。
- 形式不適合のリトライは役割ごとに1回まで。それ以外は自動リトライしません。

## 再開手順

1. `python3 harness.py --status` で状態を確認する。
2. そのまま `python3 harness.py` を再実行する。`done` の件はスキップされ、
   途中状態の件は最後に成功した役割の次から再開します（二重実行・二重消費なし）。
3. `failed` の件は自動では再実行されません。原因を確認し、直せるものは直してから
   `python3 harness.py --reset-failed` で戻してください（既存の成果物がある段階から再開します）。
4. 予算ガード stop（累積 600 credits）で止まった場合は、上限の見直しが済むまで
   再開しないでください。見直したら `config.json` の値を変更して再実行します
   （コード側で上限を勝手に引き上げることはしません）。

## verdict の正規化

reviewer が `verdict: "pass"` を返しながら issues を残すことがあります
（軽微な指摘のみで合格、という使い方）。その場合、指摘を捨てないため
ハーネスは実効 verdict を `revise` として fixer に回します。reviewer 自身の
判定は state の `verdict_raw` に保持し、review.json は原文のまま保存します。

## 予算ガード

- 累積クレジット（run-log.jsonl の実測合計）が 300 で警告（続行）、
  600 で停止（実行中の件は終えてから、新規の件に入らない）。
- preflight の消費も累積に含みます。

## 題材（初期）

spring-batch 6.1.0-RC1 の closed issue のうち、第1段階試行済みの
#3757・#4169・#4804 を除く21件。要約の想定読者は Spring Batch を
業務で2〜3年使う中堅エンジニア。入力は自前取得した原文 issue と
closing diff（#5570 のみ diff なし。本文のみで要約します）。
既存パイプライン（Claude Code版）の成果物は上書きしません
（取得結果の突き合わせ検証でのみ参照しました）。

ガイドライン準拠版の再実行は `runs-aligned/` で行いました（既存の
`runs/` は変更していません）。結果は 18件 done／1件 failed
（#5566：翻訳タイトル内のバッククォートが検証で落ち、リトライ後も
解消せず）／2件未実施（#5598・#5599：予算ガード stop 600 に達したため
開始せず）。消費は run-log 合計 609.80 credits（preflight 2回分を含む）。
再開する場合は、上限の見直し後に `python3 harness.py --runs-dir
runs-aligned` を再実行すれば残件から再開できます（#5566 は
translated.md を消してから `--reset-failed` が必要です）。