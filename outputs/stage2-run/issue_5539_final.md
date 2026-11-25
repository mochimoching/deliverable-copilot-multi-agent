# Issue #5539 要約: 未オープンの `JpaPagingItemReader` を close すると NullPointerException が発生する問題

## 概要
一度も open されていない `JpaPagingItemReader` を `close()` すると、`NullPointerException` が原因の `ItemStreamException`(`Error while closing item reader`)が発生する不具合の修正です。`doClose()` に null チェックを追加することで解消されました。Issue は closed、マイルストーンは 6.1.0-RC1、ラベルは `type: bug`、`in: infrastructure`、`for: backport-to-6.0.x` です。

## 問題
- `JpaPagingItemReader` の `entityManager` は `doOpen()` でのみ代入されますが、`doClose()` は `entityManager.close()` を無条件に呼んでいました。そのため、open されていないリーダーでは `entityManager` が null のまま NPE になります。
- Issue では、step が未実行の singleton リーダー Bean に対し、コンテキスト終了時に推論された `close` の destroy メソッドが呼ばれるケースで起こり得るとされています。
- DB なしで再現可能で、`EntityManagerFactory` を Mockito でモックし、`afterPropertiesSet()` 後に `close()` を呼ぶだけで再現します。
- 報告は main ブランチ(a3028e3c)基準です。Issue は、この close の無防備さは JSpecify 移行より前からあり、移行が原因とは見ていないと述べています。
- 同種の問題は `JpaCursorItemReader` で #5486 / #5489 として対応済みです(内容は入力に記載がありません)。

## 修正内容
コミット d2f3518093ac による変更です。

- `JpaPagingItemReader` の `doClose()` で、`entityManager` が null でない場合のみ `entityManager.close()` を呼ぶようにしました。`super.doClose()` は従来どおり常に呼ばれます。
- テストを 2 つ追加しました。
  - 未 open で `close()` しても例外が出ないこと。
  - open 後の `close()` で `EntityManager.close()` が呼ばれること。

## 利用者への影響・対応
- 入力から言えるのは、未 open のリーダーを close しても例外にならなくなる点までです。既存の open 後の close は、`EntityManager.close()` が呼ばれることがテストで確認されています。
- 該当バージョンを使っていて、step 未実行のままコンテキストが終了する構成で終了時にエラーが出ていた場合は、この修正で解消されると考えられます(推測)。
- `for: backport-to-6.0.x` ラベルがあるため 6.0.x への反映が予定されていたと読めますが、実際にバックポートされたか、影響を受けるリリース版の範囲は入力からは不明です。利用中バージョンのリリースノートでの確認をお勧めします。
- 自作の `ItemStream` / リーダーでも、`doOpen()` で初期化するリソースを `doClose()` で解放する場合は、未 open での close を考慮して null を扱うと安全です(一般的な推奨であり、Issue に記載された内容ではありません)。

## 補足
- 出典: https://github.com/spring-projects/spring-batch/issues/5539 、コミット https://github.com/spring-projects/spring-batch/commit/d2f3518093ac6cb7fd22b1ec54cd36feb8c18e7d
- コメントで hunseonglee 氏が `JpaCursorItemReader` と同様の修正で PR を出すと表明していますが、このコミットとの対応関係は入力からは確認できません。
