# JdbcJobExecutionDao.findJobExecutions は N 件の実行に対して 1 + 3N 回のクエリを発行する

**Issue番号**: #5570
**状態**: closed | **作成者**: fmbenhassine | **作成日**: 2026-09-30
**ラベル**: in: core, type: enhancement, status: for-internal-team
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5570

## 内容

**現在の動作**

`JdbcJobExecutionDao.findJobExecutions(JobInstance)` は、まずインスタンスの実行 ID をクエリし、その後 `getJobExecution(long)` を通じて各実行を個別にロードします。

```java
List<Long> jobExecutionIds = ... // 1 query
for (Long jobExecutionId : jobExecutionIds) {
      jobExecutions.add(getJobExecution(jobExecutionId)); // 3 queries each
}
```

`getJobExecution` を 1 回呼び出すごとに 3 回のクエリが発生します。実行の行に対して 1 回、そのジョブインスタンスに対して 1 回、そのジョブパラメータに対して 1 回です。つまり N 件の実行に対して 1 + 3N 回のクエリとなり、10 件の実行を持つインスタンスでは 31 回のクエリになります。

この 3 回のうち 2 回は、バッチ化するかどうかに関係なく回避可能です。

- ジョブインスタンスは、呼び出し元がメソッドの引数として渡しているため、すでに利用可能です。にもかかわらず、それは破棄され、実行ごとに 1 回ずつデータベースから読み直されています
- すべての実行のジョブパラメータは、実行ごとに 1 回ではなく、1 回のクエリでまとめて取得できます

`getLastJobExecution(JobInstance)` にも、より小さな規模で同じ問題があります。最後の実行の ID を取得した後、`getJobExecution` を経由するため、2 回で済むところが 4 回のクエリになり、渡されたインスタンスも同様に破棄されます。

**期待される動作**

実行の件数に依存しない 2 回のクエリ：インスタンスの実行の行を取得するクエリ 1 回と、`WHERE JOB_EXECUTION_ID IN (...)` でそれらの実行のパラメータを取得するクエリ 1 回です。その際、与えられた JobInstance は再ロードせずに再利用します。上記の 10 件の実行の例では、31 回のクエリが 2 回になります。

`findJobExecutions` 内の `// TODO optimize to a single query with a join if possible` が示唆するように、単一の結合クエリも検討されましたが、`BATCH_JOB_EXECUTION_PARAMS` を結合すると実行の行がパラメータの行の数だけ増えてしまい、`ResultSetExtractor` での再グループ化が必要になります。2 つのフラットなクエリのほうが良いトレードオフであるように思われます。

**コンテキスト**

これは #5495 で報告されている内容の一部です。

## コメント

### コメント 1 by fmbenhassine (2026-09-30)

5e620cc946eefd4c97a5c7fba85371954ff90e6b で解決しました
