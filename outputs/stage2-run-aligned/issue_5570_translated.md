*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# JdbcJobExecutionDao.findJobExecutionsがN件の実行に対して1 + 3N回のクエリを発行する問題

**Issue番号**: #5570
**状態**: closed | **作成者**: fmbenhassine | **作成日**: 2026-09-30
**ラベル**: in: core, type: enhancement, status: for-internal-team
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5570

## 内容

**現在の動作**

`JdbcJobExecutionDao.findJobExecutions(JobInstance)`は、まずインスタンスの実行IDをクエリで取得し、その後`getJobExecution(long)`を通じて各実行を個別にロードします。

```java
List<Long> jobExecutionIds = ... // 1 query
for (Long jobExecutionId : jobExecutionIds) {
      jobExecutions.add(getJobExecution(jobExecutionId)); // 3 queries each
}
```

`getJobExecution`の呼び出しは1回につき3つのクエリを必要とします。実行行用に1つ、そのジョブインスタンス用に1つ、そのジョブパラメータ用に1つです。したがってN件の実行に対して1 + 3N回のクエリとなり、10件の実行を持つインスタンスでは31回のクエリがかかります。

これら3つのうち2つは、バッチ化に関係なく回避可能です。

- ジョブインスタンスは、呼び出し元がメソッドの引数として渡すため既に利用可能ですが、それが破棄され、実行ごとに1回データベースから読み直されています
- すべての実行のジョブパラメータは、実行ごとに1回ではなく、1つのクエリでまとめて取得できます

`getLastJobExecution(JobInstance)`にも、より小規模ですが同じ問題があります。最後の実行のIDを取得してから`getJobExecution`を経由するため、2回で済むところが4回のクエリとなり、渡されたインスタンスも同様に破棄されています。

**期待される動作**

実行数に依存しない2回のクエリにします。1つはインスタンスの実行行を取得するクエリ、もう1つは`WHERE JOB_EXECUTION_ID IN (...)`でそれらの実行のパラメータを取得するクエリです。このとき、渡されたJobInstanceは再ロードせずに再利用します。上記の10件の実行の例では、31回のクエリが2回になります。

`findJobExecutions`内の`// TODO optimize to a single query with a join if possible`が示唆するように、単一の結合クエリも検討されました。しかし、`BATCH_JOB_EXECUTION_PARAMS`を結合すると実行行がそのパラメータ行の数だけ増えるため、`ResultSetExtractor`で再グルーピングする必要があります。フラットな2つのクエリの方がより良いトレードオフと思われます。

**コンテキスト**

これは#5495で報告されている内容の一部です。

## コメント

### コメント 1 by fmbenhassine (2026-09-30)

5e620cc946eefd4c97a5c7fba85371954ff90e6b で解決されました
