*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

[#5589](https://github.com/spring-projects/spring-batch/issues/5589) は、`MongoCursorItemReader` で `open()` を呼ぶ前に `close()` を呼ぶと、`NullPointerException` を包んだ `ItemStreamException` がスローされるバグです。

再現手順は、`MongoCursorItemReader` を作成し、`open()` を呼ばずに `close()` を呼ぶだけです。クローズすべきカーソルがないので、本来は例外を投げずに終わるべきです。実際には `this.cursor` が `null` のため `NullPointerException` が発生し、`ItemStreamException` でラップされます。

業務への影響は、次のように考えられます（Issue に記載はなく、これは推測です）。Spring Batch のステップが失敗したときの後始末で `ItemStream` の `close()` が呼ばれる流れを前提にすると、`open()` に到達する前に失敗した場合、本来のエラーの後に `close()` 由来の `ItemStreamException` が出ます。その結果、原因調査が混乱する可能性があります。

## 原因

`open()`（`doOpen()`）で MongoDB カーソルを初期化しますが、`doClose()` は初期化済みかどうかを確認せずに `this.cursor.close()` を呼んでいました。そのため `open()` 前の `close()` では `cursor` が `null` のまま参照され、`NullPointerException` が発生します。

Issue によると、`JpaCursorItemReader` と `JpaPagingItemReader` は `doClose()` で未初期化のリソースを適切に扱っているとのことです。

## 対応方針

修正コミット [bdccbf0](https://github.com/spring-projects/spring-batch/commit/bdccbf0886562dc3c755df4c6081009107b0e59b) では次の変更をしています。

- `MongoCursorItemReader.doClose()` に `null` ガードを追加し、`this.cursor != null` の場合のみ `close()` を呼ぶ
- 不要になった `@SuppressWarnings("DataFlowIssue")` を削除する
- 未オープンの `close()` が例外を出さないテストを追加する

`@SuppressWarnings` の削除は Issue に記載がなく、diff のみから確認できる変更です。

Issue のマイルストーンは 6.1.0-RC1 で、`for: backport-to-6.0.x` ラベルが付いています。そのため 6.1.0-RC1 で修正され、6.0.x へのバックポートが予定されていると読み取れます。利用側で `open()` 前の `close()` を避ける回避策を入れている場合は、修正版に上げれば不要になると考えられます。ただし、6.0.x のリリース時期は入力から分かりません。

## バグの発生タイミング

- **バグが発生した Spring Batch のバージョン**: 入力に記載なし。Issue のマイルストーンは 6.1.0-RC1 で、`for: backport-to-6.0.x` ラベルが付いています。
- **バグが発生したコミット**: 入力に記載なし（不明）。
- 参考（修正コミット。バグ混入コミットではありません）: [bdccbf0](https://github.com/spring-projects/spring-batch/commit/bdccbf0886562dc3c755df4c6081009107b0e59b)
