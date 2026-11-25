# Issue #5519 要約: `DelimitedLineTokenizer` で引用符1文字だけのフィールドが例外になる問題

## 概要
`DelimitedLineTokenizer` が、引用符(`"`)1文字だけのフィールドを含む行を処理すると `StringIndexOutOfBoundsException` を投げる不具合の修正です。修正後は、その引用符をそのまま文字列として返します。修正コミットは 8b9e2e8 で、マイルストーンは 6.1.0-RC1、ラベルに `for: backport-to-6.0.x` が付いています。

## 問題
引用符で囲まれたフィールドかどうかの判定が、フィールド(トークン)の長さではなく行全体の長さを基準にしていたことが原因です。

そのため、`a,"` のように引用符1文字だけのフィールドが行末にあると例外になります。

```java
new DelimitedLineTokenizer().tokenize("a,\"");
// java.lang.StringIndexOutOfBoundsException
```

一方、行全体が `"` だけの場合は例外にならず `"` が返っており、フィールドの位置によって挙動が食い違っていました。

## 修正内容
判定の基準を、行全体の長さからトークンの長さに改めました。

`DelimitedLineTokenizerTests.java` にはテストが2件追加されました。
- `testTokenizeWithLoneQuoteCharacterField`: `a,"` が2フィールドになり、値が `a` と `"` になることを確認します。
- `testTokenizeWithLoneQuoteCharacterLine`: `"` だけの行が1フィールドで、値が `"` になることを確認します。

## 利用者への影響・対応
`a,"` のように、引用符1文字だけのフィールドを含む行が例外にならず、`"` として読み込まれるようになります。`tokenize("\"")` の既存挙動とも揃います。

## 補足
- 利用者側で必要な対応、実運用での発生頻度、例外が `FlatFileItemReader` 側でどう扱われるかは、入力からは不明です。引用符の対応が崩れたデータで発生していた可能性はありますが、推測です。
- issue 本文では 5.x にも同じ問題があるとされていますが、5.x での修正の有無は不明です。
- 引用符以外の `quoteCharacter` を設定した場合の挙動は、テストがなく確認できません。
- あわせてコピーライト表記が更新されていますが、挙動とは無関係です。
