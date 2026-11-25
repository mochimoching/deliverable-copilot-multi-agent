# Issue #5589 要約: MongoCursorItemReader を open() 前に close() すると NullPointerException になる問題
## 概要
`MongoCursorItemReader` を `open()` せずに `close()` すると、`NullPointerException` を原因とする `ItemStreamException` が発生していました。`doClose()` に null チェックを追加し、未オープンでも例外を出さないよう修正されています(コミット bdccbf088656)。

## 問題
- `cursor` は `doOpen()` で初期化されますが、`doClose()` は初期化の有無を確認せず `this.cursor.close()` を呼んでいました。
- 再現手順: (1) `MongoCursorItemReader` を生成する、(2) `open()` を呼ばずに `close()` を呼ぶ、(3) 例外を確認する。
- 期待: 閉じる対象のカーソルがないので例外は出ない。実際: `this.cursor` が null のため `ItemStreamException`(原因は `NullPointerException`)が発生。
- issue によると、`JpaCursorItemReader` と `JpaPagingItemReader` は `doClose()` で未初期化のリソースを既に考慮しています。

## 修正内容
対象は `spring-batch-infrastructure` の `MongoCursorItemReader.java` です。
- `doClose()` を `if (this.cursor != null) { this.cursor.close(); }` に変更。

テストは `MongoCursorItemReaderTest.java` に `testCloseWithoutOpen` を追加し、`assertDoesNotThrow(reader::close)` で未オープン時の `close()` が例外を投げないことを検証しています。

## 利用者への影響・対応
- API の変更はなく、変わるのは「未オープンの `close()` で例外が出なくなる」点のみです。
- 通常どおり `open()` 後に `close()` する場合の挙動は変わりません(diff 上、既存の処理は null でない場合にそのまま実行されます)。
- 利用者側の対応は不要です。

## 補足
- ラベルは `type: bug`、`in: infrastructure`、`for: backport-to-6.0.x`、マイルストーンは 6.1.0-RC1 です。6.0.x へのバックポート用ラベルは付いていますが、実際にバックポートされたか、およびその版番号は入力からは確認できません。
- 「open 前に close」が実運用でどのような状況で起きるかは、入力に記載がありません。
- Issue: https://github.com/spring-projects/spring-batch/issues/5589
- Commit: https://github.com/spring-projects/spring-batch/commit/bdccbf0886562dc3c755df4c6081009107b0e59b
