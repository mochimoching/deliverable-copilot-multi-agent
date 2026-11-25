# ChunkOrientedStep でチャンクスキャン中に失敗した後のリスタートが、そのチャンクの残りのアイテムをスキップしてしまう

**Issue番号**: #5558
**状態**: closed | **作成者**: pius712 | **作成日**: 2026-09-26
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5558

## 内容

**バグの説明**

`ChunkOrientedStep` がチャンクのスキャン中に失敗した場合（例えば、スキャン対象のアイテムの 1 つでスキップ上限を超えた場合）、ジョブをリスタートしても、失敗前に書き込まれなかったそのチャンクのアイテムが処理されません。リスタートされたステップはそのチャンクから何も読み込まず、正常に完了するため、それらのアイテムは気づかれないまま失われます。

チャンクのスキャン中は、各アイテムが専用のトランザクションで再試行されます。コミットされるそれらのトランザクションはそれぞれ reader に対して `ItemStream#update` を呼び出しますが、その時点で reader はすでにチャンク全体を読み込んでいるため、保存される reader の状態は*チャンクの最後のアイテムの後*の位置になります。一方で、コミットされるのは失敗したアイテムより前のアイテムだけです。

Spring Batch 5 では、`FaultTolerantStepBuilder` が reader のストリームを `ChunkMonitor` に登録していました。`ChunkMonitor` は、チャンクのスキャン中は reader の状態を更新せず、代わりにオフセット（`ChunkMonitor.OFFSET`）を保存していました。リスタート時には、reader はチャンクの先頭に位置付けられ、すでにスキャン済みのアイテムは読み込まれて破棄されるため、ジョブはそれらの直後から再開されていました。`ChunkOrientedStep` にはこれに相当する仕組みがなく、`FaultTolerantStepBuilder` から移行したジョブにとってはリグレッションとなっています。

#5493 のコミットには「スキャン中の失敗はステップを失敗させるため、ジョブはリスタート可能なままである」と記載されていますが、実際にはリスタートはスキャンが停止した位置から再開されません。

**環境**

- Spring Batch 6.0.5、および c15bfcea7 時点の `main`
- Java 25、H2

**再現手順**

5 アイテムの単一チャンク、状態を保存するリスタート可能な reader（例: `FlatFileItemReader`、`JdbcCursorItemReader`、または任意の `AbstractItemCountingItemStreamItemReader`）、スキップ可能な例外でアイテム `2` と `4` に対して失敗する writer、そして `skipLimit(1)` を使用します。

```java
new ChunkOrientedStepBuilder<String, String>(jobRepository, 5)
	.reader(restartableReader) // items 1, 2, 3, 4, 5
	.writer(chunk -> {
		for (String item : chunk) {
			if (faultyItems.contains(item)) { // "2" and "4"
				throw new IllegalStateException("Simulated write error for item: " + item);
			}
			jdbcTemplate.update("INSERT INTO delivery (item_number) VALUES (?)", item);
		}
	})
	.transactionManager(transactionManager)
	.faultTolerant()
	.skip(IllegalStateException.class)
	.skipLimit(1)
	.build();
```

1. ジョブを実行します。チャンクの書き込みが失敗し、チャンクがスキャンされます。`1` は書き込まれ、`2` はスキップされ、`3` は書き込まれ、`4` でスキップ上限を超えてステップが FAILED になります。アイテム `1` と `3` はコミットされます。保存された reader の状態（`read.count`）は `5` です。
2. データを修正（`faultyItems.clear()`）して、ジョブをリスタートします。

完全なテストケースは、リンクされたプルリクエスト（`ChunkOrientedStepScanModeRestartIntegrationTests`）にあります。

**期待される動作**

リスタートはアイテム `3` の後から再開されます。アイテム `4` と `5` が書き込まれ、ジョブは `1, 3, 4, 5` が書き込まれた状態で完了します。これは、同等の `FaultTolerantStepBuilder` 構成での Spring Batch 5.2.4 の動作です。

**実際の動作**

リスタートされたステップはアイテムを 1 つも読み込まず（`readCount=0`）、ステータス `COMPLETED` で完了します。アイテム `4` と `5` は書き込まれることはなく、失われたことを示すものは何もありません。


## コメント

### コメント 1 by fmbenhassine (2026-09-29)

これは妥当な issue です。ご報告ありがとうございます！

v5 で試したところ、確かに動作が異なります。ただし、次の記述は正確ではありません。

> the job completes with 1, 3, 4, 5 written. This is what Spring Batch 5.2.4 does

v5 での出力は 1, 3, 3, 4, 5 です。アイテム 3 が二重に書き込まれます。`ChunkMonitor.incrementOffset()` はスキャン対象アイテムの書き込みが成功したときにしか呼ばれないため、2 をスキップしてもオフセットは進まず、3 ではなく 2 で終わります。そのためリスタート時には 2 回分の読み込みが再生され、3 が二重に書き込まれます。

つまり v5 と比べると、これは重複からサイレントなデータ損失へのリグレッションであり、オフセットのセマンティクスを元に戻すのではなく修正すべきです（オフセットはコミットされたアイテムではなく、読み込み位置を数えるべきです）。PR #5559 はそのための正しい方向に向かっているようです。

次のリリースで修正を計画します。
