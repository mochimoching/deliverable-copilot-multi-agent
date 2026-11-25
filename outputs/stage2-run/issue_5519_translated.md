# `DelimitedLineTokenizer` は、フィールドが単一のクォート文字の場合に `StringIndexOutOfBoundsException` をスローする

**Issue番号**: #5519
**状態**: closed | **作成者**: hunseonglee | **作成日**: 2026-09-03
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5519

## 内容

**バグの説明**
`DelimitedLineTokenizer.substringWithTrimmedWhitespaceAndQuotesIfQuotesPresent` は、トークンがクォートで囲まれているかどうかを次のように判定しています:

```java
if ((line.length() >= 2) && isQuoteCharacter(line.charAt(start))
        && isQuoteCharacter(line.charAt(start + len - 1))) {
```

この長さのガードは、*トークン*ではなく行全体の長さを確認しています。クォート文字そのものである1文字のトークン(例: `a,"` の最後のフィールド)の場合、2つのクォート判定が同じ文字に対して成立し、`endIndex` が `-1` になり、`line.substring(beginIndex, beginIndex - 1)` が `StringIndexOutOfBoundsException` をスローします。

これは行全体が対象の場合と一貫していません。`tokenize("\"")` は、そこでは行の長さのガードが false になるため、すでにリテラルの `"` を返します。

**環境**
`cb69762` 時点の Spring Batch `main`(6.0.x)。5.x にも存在します。JDK 21。

**再現手順**
```java
new DelimitedLineTokenizer().tokenize("a,\"");
// java.lang.StringIndexOutOfBoundsException: Range [3, 2) out of bounds for length 3
```

**期待される動作**
単独のクォートのフィールドは、`tokenize("\"")` と一貫して、リテラル(`"`)として返されます。ガードはトークンの長さ(`len >= 2`)を確認すべきです。修正とテストを含む PR を提出する予定です。
