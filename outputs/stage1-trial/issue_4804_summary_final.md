# Spring Batch #4804 要約: JDBC DAO の名前付きパラメータ化と JdbcClient への移行

- Issue: #4804（closed）／ラベル: `in: core`, `type: enhancement`, `related-to: job-repository`／マイルストーン: 6.1.0-RC1
- 経緯: quaff が提案し、fmbenhassine が「v6 の候補」として賛同。quaff が関連する改善 PR を先行して出し、本件はその後に進める流れになった。

## 概要

JobRepository 用の JDBC DAO で、位置パラメータ（`?`）を名前付きパラメータへ、JDBC 呼び出しを fluent API の `JdbcClient`（メソッドチェーンで書ける JDBC クライアント）へ移行したリファクタリングです。内部処理が中心ですが、公開／継承向け API の変更（`setJdbcClient()` の追加、`getJdbcTemplate()` の廃止予定化、`afterPropertiesSet()` の検証追加）を含みます。

なお `setJdbcTemplate()` は `JdbcOperations` を受け取るセッターです。以降、この型を「`JdbcOperations`（`setJdbcTemplate()` で設定するもの）」と表記します。

## 問題・背景

- 位置パラメータだと、同じ値を SQL 中で複数回使うとき Java 側でも同じ引数を重複して渡す必要がある（JDBC の PreparedStatement 自体は重複を解消しない）。
- 名前付きパラメータ／`JdbcClient` への移行が望ましいとして、メンテナが賛同した。
- （差分からの推測）位置パラメータの順序依存や `JdbcTemplate` 中心の記述が、可読性・冗長性の面で改善対象だった可能性がある。issue 本文に書かれた根拠ではない。

## 修正内容

**共通基底クラス `AbstractJdbcBatchMetadataDao`**
- `JdbcClient` フィールドと `setJdbcClient()`／`getJdbcClient()` を追加。
- `setJdbcTemplate()` は内部で `JdbcClient.create(...)` も設定する。
- `getJdbcTemplate()` は `@Deprecated(forRemoval = true)` になり、`@Nullable` を外して `Assert.state` で必須化。
- `afterPropertiesSet()` に `jdbcClient != null` の検証を追加。

**各 DAO（`JdbcJobExecutionDao`、`JdbcJobInstanceDao`、`JdbcStepExecutionDao`、`JdbcExecutionContextDao`）**
- 名前付きパラメータ化: SQL を `:jobExecutionId`、`:jobInstanceId`、`:jobName`、`:version` などに変更。
- 重複パラメータの解消: `JdbcJobExecutionDao` の `GET_LAST_JOB_EXECUTION_ID` は `JOB_INSTANCE_ID` を 2 回渡していたが、`:jobInstanceId` 1 回の指定になった。`JdbcJobInstanceDao` の `FIND_LAST_JOB_INSTANCE_BY_JOB_NAME` も `jobName` の重複が解消した。
- 例外処理から Optional への置換: `EmptyResultDataAccessException` の try/catch を `.optional()` ベース（`.orElse(null)` など）に置換。
- INSERT/UPDATE は、型指定付きの位置パラメータ（`.param(n, value, Types.X)`）のまま。名前付き化は段階的で、全面移行ではない。

## 利用者への影響

- **公開／継承向け API の変更（サブクラスや独自構成の利用者は要注意）**
  - 自前の DAO サブクラスで `getJdbcTemplate()` を使っていると、廃止予定（forRemoval）の警告が出る。`getJdbcClient()` への移行が必要。
  - `afterPropertiesSet()` は `JdbcOperations` と `JdbcClient` の両方を必須とする。`setJdbcTemplate()` で `JdbcOperations` を設定すれば `JdbcClient` は自動で作られるが、`JdbcOperations` を設定せず `setJdbcClient()` だけを設定しても足りず、初期化に失敗する。
- **回帰の可能性（要確認）**: `JdbcJobInstanceDao.getJobInstanceIds` は、差分上 `getQuery()` を通さず定数をそのまま渡しているように見える。テーブル接頭辞を設定している利用者では、接頭辞が置換されず別テーブルを参照する、または失敗する恐れがある。断定はできないため、実コードでの確認が必要。
- **挙動への影響が小さいと見込まれる変更**: 実行される SQL の論理的な意味は変えない意図の変更だが、上記の `getJobInstanceIds` の件があるため「挙動は変わらない」とは断定できない。結果なし時の例外から Optional への置換について、該当なし時の戻り値はメソッドごとに確認が必要（例: `JdbcExecutionContextDao` は `null` ではなく `orElseGet(ExecutionContext::new)` で空の `ExecutionContext` を返す）。

## 注意点・未確認事項

- `getJobInstanceIds` の `getQuery()` 除去は上記のとおり未確認。
- 移行後の回帰確認では、テーブル接頭辞を設定した構成と、利用する各種 DB での動作確認が必要。
