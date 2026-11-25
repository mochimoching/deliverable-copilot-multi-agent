*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

[#5519](https://github.com/spring-projects/spring-batch/issues/5519) は、`"` だけのフィールドを含む行（例 `a,"`）を分割すると、`DelimitedLineTokenizer` が `StringIndexOutOfBoundsException` を投げる不具合です。

再現例（issue 記載）:

```java
new DelimitedLineTokenizer().tokenize("a,\"");
// java.lang.StringIndexOutOfBoundsException: Range [3, 2) out of bounds for length 3
```

- `"`（行全体が引用符1文字）: 例外にならず `"` を返す。
- `a,"`（最後のフィールドが引用符1文字）: `StringIndexOutOfBoundsException`。期待値は `a` と `"` の2フィールド。

同じ「引用符1文字」でも、行全体なら成功し、フィールドなら例外になります。

影響が出るのは、引用符1文字だけのフィールドを含む CSV（不正な形式や途中で切れた行など）を読む場合です。`FlatFileItemReader` で読むと `FlatFileParseException` になりうると考えられますが、未確認です。その場合、skip 設定がなければ step が失敗し、再実行しても同じ行で失敗します。

## 原因

`substringWithTrimmedWhitespaceAndQuotesIfQuotesPresent` が、トークンが引用符で囲まれているかを判定する条件のうち、長さのガードが**トークンではなく行全体**の長さを見ていたためです。

```java
if ((line.length() >= 2) && isQuoteCharacter(line.charAt(start))
        && isQuoteCharacter(line.charAt(start + len - 1))) {
```

1文字のトークンでは先頭も末尾も同じ文字になり、`len - 2` が `-1` になって `substring` の範囲が不正になります。

行全体が `"` だけの場合は `line.length() >= 2` が false になり、例外を避けられていました。

## 対応方針

`a,"` は例外ではなく `a` と `"` の2フィールドになります。例外を前提に skip や異常終了へ頼っている処理があれば、挙動が変わります。

**issue 本文の方針**: ガードをトークンの長さ（`len >= 2`）で判定するように修正し、単独の引用符フィールドを `tokenize("\"")` と一貫してリテラル `"` として返す。

**diff の内容**（コミット [8b9e2e8](https://github.com/spring-projects/spring-batch/commit/8b9e2e84742582d022845f4c6703cc6d69618f31)）:

- `DelimitedLineTokenizer` の `substringWithTrimmedWhitespaceAndQuotesIfQuotesPresent` で、条件を `line.length() >= 2` から `len >= 2` に変更。
- `DelimitedLineTokenizerTests` に、`a,"` が `a` と `"` の2フィールドになること、`"` が1フィールドで `"` になることを確認するテストを2件追加。

## バグの発生タイミング

- **発生バージョン**: `cb69762` 時点の Spring Batch `main`（6.0.x）で確認され、5.x にも存在する（具体的な発生バージョンは不明）。
- **バグが発生したコミット**: 特定できていません。
- 修正コミットは [8b9e2e8](https://github.com/spring-projects/spring-batch/commit/8b9e2e84742582d022845f4c6703cc6d69618f31)（マイルストーン 6.1.0-RC1）です。ラベルに `for: backport-to-6.0.x` があります。
