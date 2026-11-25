# リスナーの例外は scan モードではスキップ可能だが、それ以外では致命的である

**Issue番号**: #5585
**状態**: closed | **作成者**: fmbenhassine | **作成日**: 2026-10-12
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5585

## 内容

これは https://github.com/spring-projects/spring-batch/discussions/5578 から生まれたものです。

リスナーは例外をスローするようには設計されていません。リスナーのどのメソッドも例外を宣言しておらず、リファレンスドキュメントでも `ChunkListener` について既に次のように述べられています: "Errors must be handled in the implementation or the step will terminate"。これは fault-tolerant なチャンク指向ステップの動作でもあります。チャンクの読み取り、処理、書き込み中にリスナーがスローした例外は、ステップを失敗させます。

ただし一つ例外があります。書き込み失敗後にチャンクが scan される際、write リスナーがスローした例外は、scan 対象のアイテムの書き込み失敗として扱われます。そのアイテムはスキップされ、ステップは続行されます。つまり、同じリスナーのバグが、scan 中はスキップ可能であるのに、チャンクの最初の書き込みでは致命的になります。

これは件数の不整合にもつながります。`afterWrite` リスナーが失敗したアイテムは、書き込み済みとしてもスキップ済みとしてもカウントされます。

**期待される動作**

scan はリスナーの例外をスキップしないようにし、あらゆる場面で致命的になるようにするべきです。ステップは失敗し、他のリスナー失敗の場合と同様に再開可能な状態のままであるべきです。また、`ItemReadListener`、`ItemProcessListener`、`ItemWriteListener` の Javadoc とリファレンスドキュメントにも、リスナーはスローするように設計されていないことを明記するべきです。リスナーがスローした例外は skip や retry の対象にはならず、ステップを終了させます。現状では `ChunkListener` のみがこれを文書化しています。

**備考**

`StepListenerFailedException` は、ステップリスナーが例外をスローするようには設計されていないため、既に削除予定として非推奨化されています (6.0 以降)。リスナー内の例外は、フレームワークによって read/process/write の失敗として扱われるべきではなく (したがって retry/skip ポリシーの対象とすべきではなく)、致命的なものとみなされるべきです。v5.x ではこの点が一貫していませんでしたが、v6 で修正されました (scan のみが唯一の残りです)。
