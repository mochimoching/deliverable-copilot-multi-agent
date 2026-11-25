# Issue #5570 要約: `JdbcJobExecutionDao` の実行履歴取得で発行されるクエリ数を 1 + 3N 回から 2 回に削減

## 概要
`JdbcJobExecutionDao.findJobExecutions(JobInstance)` は、N 件の `JobExecution` を取得するのに 1 + 3N 回のクエリを発行していました。この issue はそれを、件数に依存しない 2 回に減らす改善です。`getLastJobExecution(JobInstance)` も同種の無駄があり、4 回から 2 回に減らす対象です。状態は closed、マイルストーンは 6.1.0-RC1 で、コミット 5e620cc946eefd4c97a5c7fba85371954ff90e6b で解決されたとコメントされています。issue #5495 で報告されている問題の一部への対応です(#5495 の詳細は入力にないため不明)。

## 問題
`findJobExecutions(JobInstance)` は、まずインスタンスに属する実行 ID を 1 クエリで取得し、各 ID について `getJobExecution(long)` を呼んでいました。`getJobExecution(long)` は 1 回につき 3 クエリを発行します(実行行、`JobInstance`、ジョブパラメータ)。そのため N 件で 1 + 3N 回になり、10 件の実行を持つインスタンスでは 31 回になります。

issue では、次の 2 点が不要な処理として挙げられています。
- 呼び出し元が `JobInstance` を引数で渡しているのに、それを捨てて実行ごとに DB から読み直している。
- 全実行のジョブパラメータは、実行ごとではなく 1 クエリでまとめて取得できる。

`getLastJobExecution(JobInstance)` も、最新実行の ID を取得した後に `getJobExecution` を経由するため、同じく引数の `JobInstance` を捨てており、最新実行 ID の取得と `getJobExecution` 経由で計 4 クエリを発行していました(2 クエリで足りる)。なお、この 4 クエリの内訳は issue に明示されておらず、推論によるものです。

## 修正内容
コミット 5e620cc で解決済みとされていますが、差分が入力にないため、実際にどのように実装されたかは未確認です。以下は issue に記載された期待動作(提案)です。
- クエリを実行数に依存しない 2 回にする。1 回目はインスタンスの実行行の取得、2 回目は `WHERE JOB_EXECUTION_ID IN (...)` による該当実行のパラメータ(`BATCH_JOB_EXECUTION_PARAMS`)の一括取得。
- 引数で渡された `JobInstance` を再利用し、読み直さない。
- 10 件の例では 31 回が 2 回になる。

JOIN で 1 クエリにまとめる案(`findJobExecutions` 内の `// TODO optimize to a single query with a join if possible`)にも触れられています。ただし `BATCH_JOB_EXECUTION_PARAMS` を JOIN すると実行行がパラメータ行数分に増え、`ResultSetExtractor` での再グルーピングが必要になります。このため、フラットな 2 クエリの方が良いトレードオフと考えられる、と issue で述べられています。

実装の詳細(`IN` 句の要素数上限への対応、追加されたテスト、変更されたメソッドの全体像)は、差分が入力になく不明です。

## 利用者への影響・対応
issue 本文には利用者向けの影響や対応が書かれておらず、API 互換性や性能への影響も入力からは確認できません。

## 補足
- ラベル: `in: core`、`type: enhancement`
- 作成者: fmbenhassine、作成日: 2026-09-30
- URL: https://github.com/spring-projects/spring-batch/issues/5570
- `input_diff.txt` はなく、本要約は issue 本文とコメントのみに基づきます。
