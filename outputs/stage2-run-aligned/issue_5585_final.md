*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

[#5585](https://github.com/spring-projects/spring-batch/issues/5585) は、`ChunkOrientedStep` のフォールトトレラントなチャンク指向ステップにおいて、**リスナーがスローした例外の扱いが場面によって不整合になっている**という課題です。発端は [Discussion [#5578](https://github.com/spring-projects/spring-batch/issues/5578)](https://github.com/spring-projects/spring-batch/discussions/5578) です。

### 前提：リスナーは例外をスローしない設計

- リスナーのメソッドは例外を宣言しておらず、リファレンスでも `ChunkListener` について「エラーは実装内で処理しなければならず、そうしないとステップは終了する」と記載されています。
- 通常のチャンクの読み取り・処理・書き込み中にリスナーが例外をスローすると、ステップは失敗します（致命扱い）。リトライ/スキップの対象にはなりません。
- `StepListenerFailedException` は同じ理由で 6.0 以降非推奨・削除予定です。
- issue 本文によると、v5.x ではこの扱いが一貫していませんでしたが、v6 で修正され、スキャン中の書き込みだけが残っていました。

### 何が問題か

スキャンとは、書き込み失敗後に、チャンクを1件ずつ書き直して失敗アイテムを特定する処理です（`ChunkOrientedStep` の `scan()` メソッド。スキップ設定が有効なときのみ動作します）。このスキャン中だけ、書き込みリスナー（`beforeWrite` / `afterWrite`）の例外が「そのアイテムの書き込み失敗」として扱われ、アイテムがスキップされてステップが続行していました。

| 場面 | リスナー例外の扱い（修正前） | 修正後 |
|---|---|---|
| 通常のチャンク書き込み | 致命（ステップ失敗） | 変更なし |
| スキャン中の1件書き込み | 書き込み失敗としてスキップ可能 | 致命（ステップ失敗） |

### 影響

- スキップ設定を有効にし、書き込みリスナーを使っているジョブでは、修正後は従来スキップされていたリスナー例外がステップ失敗になります。
- アップグレード前に、リスナー内の例外処理と `skipLimit` の設定を確認してください。
- `afterWrite` で失敗したアイテムが書き込み済みとスキップ済みの両方に計上されていた件数不整合（writeCount と skipCount の二重計上）は解消されます。

## 原因

リスナーの例外が書き込み失敗と区別されないままスキップ判定に回っていたことが原因です。`ChunkOrientedStep` の `scan()` で、`beforeWrite`、`itemWriter.write`、`afterWrite` が同じ `try` 内にあり、`catch (Exception)` が一括して書き込み失敗として処理していました。

## 対応方針

スキャンでもリスナー例外を致命にし、Javadoc とリファレンスに明記する方針です（コミット [9a2ad579e74f](https://github.com/spring-projects/spring-batch/commit/9a2ad579e74f9782caecb838525a88b6032d7198)）。

### コード修正（`ChunkOrientedStep#scan`）
- `beforeWrite` / `afterWrite` の呼び出しを書き込み失敗の判定範囲から外し、リスナー例外はスキップ判定せずそのまま致命扱いにしました。
- `itemWriter.write` 自体の失敗は、従来どおりスキップ判定の対象です。

### ドキュメント修正
- `ItemReadListener` / `ItemProcessListener` / `ItemWriteListener` の Javadoc に「例外をスローする設計ではない。スキップ/リトライの対象外で、ステップを終了させる」旨の Note を追加しました（従来は `ChunkListener` のみ記載）。
- `intercepting-execution.adoc` に同趣旨の NOTE を追加しました。

### テスト
通常書き込み・スキャンの双方でリスナー例外が致命になること、書き込み自体の失敗は従来どおりスキップ可能なことを確認しています。

### 注意点
issue 本文の「再開可能な状態のまま」は、テストでは `FAILED` と `FatalStepExecutionException` までしか確認しておらず、再開可能性は直接検証されていません。

## バグの発生タイミング

- **発生バージョン**: 導入バージョンは不明です。6.1.0-RC1 で修正され、ラベル（`for: backport-to-6.0.x`）から 6.0.x へのバックポートが予定されています。6.0.x を使っている場合は影響を受ける可能性があります。
- **発生コミット**: 入力に記載がありません。
- 参考（修正コミット）: [9a2ad579e74f](https://github.com/spring-projects/spring-batch/commit/9a2ad579e74f9782caecb838525a88b6032d7198)
