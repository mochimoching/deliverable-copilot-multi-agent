# 成果物一式 — Copilot マルチエージェント環境（2026-11-18）

Copilot マルチエージェント環境の実装一式です。セットアップは `docs/setup-guide.md` の手順に従ってください。

## 構成

| パス | 内容 |
|---|---|
| `.github/agents/` | エージェント定義5種（translator／planner／writer／reviewer／fixer）。リポジトリにそのまま配置できる形 |
| `stage1-README.md` | 第1段階スターターパックの説明と前提 |
| `TRIAL.md` | 第1段階試行の記録（実施済み分を含む） |
| `stage2-harness/` | 第2段階ハーネスの実装（harness.py／fetcher.py／copilot_runner.py／validate.py／config.json／README）。GitHub からの取得→翻訳→計画→執筆→レビュー→修正→検証まで一気通貫。モデルは claude-sonnet-5.5 固定、予算ガード warn 300／stop 600 |
| `docs/setup-guide.md` | **セットアップ手順**（事前確認→定義配置→VS Code試行→CLI導入→ハーネス配置→運用ルール→チェックリスト） |
| `docs/stage2-harness-design.md` | 第2段階設計書（全12章・決定事項含む） |
| `docs/copilot-multi-agent-harness-report.pdf` | 本体レポート第2版（A4・13ページ） |
| `docs/ai-engineering-stages-report.pdf` | AIエンジニアリングの段階レポート（A4・11ページ） |
| `outputs/stage1-trial/` | 第1段階試行の成果物（要約 final 3件＋review JSON 3件） |
| `outputs/stage2-run/` | 第2段階本実行の成果物（要約 final 21件＋翻訳 translated 21件＋state.json）。21件すべて検証通過 |
| `outputs/stage2-run-aligned/` | ガイドライン準拠版の再実行成果物（要約 final 18件＋翻訳 translated 18件＋state.json）。ガイドライン全文をプロンプトに埋め込み、構成は「課題概要／原因／対応方針」、AI明示・#参照リンク化つき。残り3件（#5566・#5598・#5599）は予算ガード停止とタイトル形式のため未完了 |

## 実証結果の要点

- 第1段階：4役割×3件を Copilot CLI で完走。reviewer が writer の日付誤り・根拠のない断定を検出。
- 第2段階：残り21件を自作ハーネスで完走。検証8項目すべて通過、予算ガード warn 300 が設計どおり発動（stop 600 には未達）。その後、取得工程（GitHub から直接取得し、既存の取得済みデータと全件バイト一致を確認）と翻訳工程（21件すべてコードブロック完全一致で検証通過）を追加し、まっさらな状態から2件で一気通貫の実証済み。
- 既知の仕様差：CLI 1.0.113 では `.agent.md` の `handoffs` が無視される（VS Code では有効）。役割遷移は第1段階では人が、第2段階ではハーネスが実行する。
