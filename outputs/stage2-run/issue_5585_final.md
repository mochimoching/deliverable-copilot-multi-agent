# Issue #5585 要約: スキャン時のみスキップ可能だった listener 例外を、他の場面と同様に致命的として扱うよう統一

## 概要
フォールトトレラントな `ChunkOrientedStep` において、書き込み失敗後のスキャン時だけ write listener の例外がスキップ対象になっていた不整合を解消した修正です。listener の例外はどの場面でもステップを失敗させる扱いに統一され、あわせて `ItemReadListener`・`ItemProcessListener`・`ItemWriteListener` の Javadoc と reference documentation に「listener は例外を投げない設計」である旨が追記されました。ラベルは `type: bug` / `in: core` / `for: backport-to-6.0.x`、マイルストーンは 6.1.0-RC1 です。

## 問題
- listener は例外を投げない設計で、`ChunkListener` には「エラーは実装側で処理しないとステップが終了する」と既に記載されていました。read/process/write 中の listener 例外はステップを失敗させるのが本来の挙動です。
- 例外が一つだけありました。chunk の書き込み失敗後にアイテムを 1 件ずつ書き直す「スキャン」では、write listener が投げた例外がそのアイテムの書き込み失敗と見なされ、アイテムがスキップされてステップが継続していました。同じ listener のバグが、スキャン中はスキップ可能、chunk の最初の書き込みでは致命的、という不整合を生んでいました。
- `afterWrite` が失敗したアイテムが「written」と「skipped」の両方にカウントされる、カウントの不整合もありました。

## 修正内容
- スキャン時も、listener 例外はスキップ判定の対象とせず、ステップを失敗させるようにしました。
- 書き込み件数とスキップ件数の二重カウントを解消しました。
- `ItemReadListener`・`ItemProcessListener`・`ItemWriteListener` の Javadoc に、「例外を投げる設計ではなく、メソッドが投げた例外は read/process/write の失敗とは見なされず、skip/retry の対象にならず、ステップを終了させる」という Note を追加しました。
- `spring-batch-docs` の `intercepting-execution.adoc` に同趣旨の NOTE を追加しました。
- `ChunkOrientedStepTests` にテストを追加し、次の 2 点を確認しています。
  - listener 例外はどの場面でもステップを `FAILED` にすること。
  - listener にバグがない通常の書き込み失敗は、従来どおりスキップ可能であること。

## 利用者への影響・対応
- listener 内で例外が発生しうる場合は、listener の実装側で処理してください。例外を投げるとスキップ/リトライの対象にならず、ステップが失敗します。
- スキップ設定を有効にしている fault-tolerant なステップで write listener にバグがあると、これまではスキャン時にアイテムが静かにスキップされていた可能性があります。修正後はステップ失敗として表面化します(この点は diff からの推測を含みます)。
- issue は、失敗したステップは他の listener 失敗時と同様に再起動可能であるべきと述べています。ただしテストで確認されているのは `FAILED` 状態までで、再起動の実挙動は検証されていません。

## 補足
- `StepListenerFailedException` は 6.0 から deprecated for removal です。issue は、listener の例外をフレームワークが read/process/write の失敗として扱わず致命的とすべきという背景として触れており、v5.x は不整合があり v6 で修正済みで、スキャンが唯一の残りだった、と説明しています。
- 実際に 6.0.x へバックポートされたかどうかは、入力からは不明です。
- 出典: https://github.com/spring-projects/spring-batch/issues/5585 、コミット `9a2ad579e74f`
