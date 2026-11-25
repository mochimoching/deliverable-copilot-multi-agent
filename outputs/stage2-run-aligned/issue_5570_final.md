*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

`JdbcJobExecutionDao` の `findJobExecutions(JobInstance)` と `getLastJobExecution(JobInstance)` が、ジョブ実行（`JobExecution`）の件数に比例した数のSQLを発行していました。これを一定数（2回）に減らす改善（enhancement）です。N+1 になっていた、という整理です。

| メソッド | 現状のクエリ数 | 期待されるクエリ数 |
|---|---|---|
| `findJobExecutions(JobInstance)` | 1 + 3N（10件のジョブ実行なら31回） | 2回（件数に依存しない） |
| `getLastJobExecution(JobInstance)` | 4回 | 2回 |

この課題は [#5495](https://github.com/spring-projects/spring-batch/issues/5495) の一部です。

**業務への影響**

- ジョブ実行の履歴が多いジョブほど、DBへの往復回数の削減が効きます。
- 本 issue は 6.1.0-RC1 で解決済みとコメントされており、issue からは、バージョンアップで反映され利用側のコード変更は不要と読み取れます。
- 返される `JobExecution` の内容が変わらないかどうかは、issue からは確認できません。
- 再起動判定など、どの呼び出し元で効くかも issue には書かれていないため、影響の大きさは分かりません。

修正内容は issue 本文とコメントに基づきます。

## 原因

- `findJobExecutions` は、引数で受け取った `JobInstance` を使わず、ジョブ実行のIDだけを取得し、各IDを `getJobExecution(long)` で個別に読み込んでいました。1件あたり3クエリ（ジョブ実行行、ジョブインスタンス、ジョブパラメータ）です。
- ジョブパラメータは1回のクエリでまとめて取得できるのに、ジョブ実行ごとに取得していました。
- `getLastJobExecution` も、最後のジョブ実行のIDを取得してから `getJobExecution` を呼ぶため、渡された `JobInstance` を使わず読み直していました。2回で済むところが4回になっていました。

## 対応方針

期待される動作は次のとおりです。

- インスタンスのジョブ実行行を取得するクエリ1回と、`WHERE JOB_EXECUTION_ID IN (...)` でそれらのパラメータを取得するクエリ1回、合わせて2回にする
- 渡された `JobInstance` は再ロードせずに再利用する

`findJobExecutions` 内の `// TODO optimize to a single query with a join if possible` が示す単一の結合クエリも検討されました。しかし `BATCH_JOB_EXECUTION_PARAMS` を結合すると、1つのジョブ実行に複数のパラメータがある場合に同じジョブ実行行が複数回返ります。それを1件にまとめ直す処理（`ResultSetExtractor` での再グルーピング）が必要で、コードが複雑になるため、2回に分ける方式が選ばれました。この判断はメンテナ（fmbenhassine）によるものです。

本 issue は 6.1.0-RC1 で、[コミット 5e620cc](https://github.com/spring-projects/spring-batch/commit/5e620cc946eefd4c97a5c7fba85371954ff90e6b) により解決されたとコメントされています。
