*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# ChunkOrientedStepでチャンクのスキャン中に失敗した後の再起動時に、チャンクの残りのアイテムがスキップされる

**Issue番号**: #5558
**状態**: closed | **作成者**: pius712 | **作成日**: 2026-09-26
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5558

## 内容

**バグの説明**

`ChunkOrientedStep`がチャンクのスキャン中に失敗した場合(たとえば、スキャンされたアイテムの1つでスキップ上限を超えた場合)、ジョブを再起動しても、失敗前に書き込まれなかったそのチャンクのアイテムは処理されません。再起動されたステップはそのチャンクから何も読み込まずに正常に完了するため、それらのアイテムは気付かれないまま失われます。

チャンクのスキャン中、各アイテムはそれぞれ独自のトランザクションで再試行されます。コミットされるそれらのトランザクションのそれぞれが、リーダーに対して`ItemStream#update`を呼び出しますが、その時点でリーダーはすでにチャンク全体を読み込んでいるため、保存されるリーダーの状態は*チャンクの最後のアイテムの後*の位置になります。一方、コミットされるのは失敗したアイテムより前のアイテムだけです。

Spring Batch 5では、`FaultTolerantStepBuilder`がリーダーのストリームを`ChunkMonitor`に登録していました。`ChunkMonitor`はチャンクのスキャン中にリーダーの状態を更新せず、代わりにオフセット(`ChunkMonitor.OFFSET`)を保存していました。再起動時には、リーダーがチャンクの先頭に位置付けられ、すでにスキャン済みのアイテムは読み込まれて破棄されるため、ジョブはそれらの直後から再開されました。`ChunkOrientedStep`にはこれに相当する仕組みがないため、`FaultTolerantStepBuilder`から移行したジョブにとってこれはリグレッションです。

[#5493](https://github.com/spring-projects/spring-batch/issues/5493) のコミットには「スキャン中の失敗はステップを失敗させるため、ジョブは再起動可能なままである」と記載されていますが、実際には、再起動してもスキャンが停止した位置から再開されません。

**環境**

- Spring Batch 6.0.5、および c15bfcea7 時点の`main`
- Java 25、H2

**再現手順**

5アイテムからなる単一のチャンク、再起動可能なリーダー(状態を保存する任意のリーダー。たとえば`FlatFileItemReader`、`JdbcCursorItemReader`、または任意の`AbstractItemCountingItemStreamItemReader`)、アイテム`2`と`4`でスキップ可能な例外を発生させるライター、そして`skipLimit(1)`を用意します。

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

1. ジョブを実行します。チャンクの書き込みが失敗し、チャンクがスキャンされます。`1`は書き込まれ、`2`はスキップされ、`3`は書き込まれ、`4`はスキップ上限を超えてステップが失敗します。アイテム`1`と`3`はコミットされます。保存されたリーダーの状態(`read.count`)は`5`です。
2. データを修正し(`faultyItems.clear()`)、ジョブを再起動します。

完全なテストケースは、リンクされたプルリクエストにあります(`ChunkOrientedStepScanModeRestartIntegrationTests`)。

**期待される動作**

再起動はアイテム`3`の後から再開されます。アイテム`4`と`5`が書き込まれ、ジョブは`1, 3, 4, 5`が書き込まれた状態で完了します。これは、同等の`FaultTolerantStepBuilder`の設定を使用した Spring Batch 5.2.4 の動作です。

**実際の動作**

再起動されたステップはアイテムを1つも読み込まず(`readCount=0`)、ステータス`COMPLETED`で完了します。アイテム`4`と`5`は書き込まれず、それらが失われたことを示すものは何もありません。


## コメント

### コメント 1 by fmbenhassine (2026-09-29)

これは妥当な課題です。ご報告ありがとうございます。

v5 で検証したところ、確かに動作が異なります。ただし、次の部分は正確ではありません。

> ジョブは 1, 3, 4, 5 が書き込まれた状態で完了します。これは Spring Batch 5.2.4 の動作です

v5 では、出力は 1, 3, 3, 4, 5 になります。アイテム3の書き込みが重複します。`ChunkMonitor.incrementOffset()`は、スキャンされたアイテムの書き込みが成功した場合にのみ呼び出されるため、2をスキップしてもオフセットは進みません。オフセットは3ではなく2で終わり、再起動時に2回分の読み込みが再実行され、3が2回書き込まれます。

したがって、v5 と比較すると、これは重複からサイレントなデータ損失へのリグレッションであり、オフセットの動作を元に戻すのではなく、オフセットのセマンティクスを修正すべきです(オフセットはコミットされたアイテムではなく、読み込み位置を数えるべきです)。PR [#5559](https://github.com/spring-projects/spring-batch/issues/5559) はそのための正しい方向に進んでいるようです。

次のリリースで修正を計画します。
