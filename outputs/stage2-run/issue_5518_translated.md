# strict モードの `FixedLengthTokenizer` が、開放範囲の開始位置が最初の範囲の min 以下の場合に行を拒否する

**Issue番号**: #5518
**状態**: closed | **作成者**: hunseonglee | **作成日**: 2026-09-03
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5518

## 内容

**バグの説明**
`FixedLengthTokenizer#setColumns` の Javadoc には次のように記載されています。「最後の範囲が開放（open）である場合、行の残りの部分がその列に読み込まれる（strict フラグの設定に関係なく）。」しかし、`calculateMaxRange` は、上限のない範囲の min がこれまでに見た実行中の最大値より *厳密に大きい* 場合にのみ、tokenizer を open とマークします。

```java
upperBound = range.getMin();
if (upperBound > maxRange) {
    open = true;
}
```

`maxRange` は `ranges[0].getMin()` で初期化されるため、単一の開放列 — `setColumns(new Range(1))`、つまり「行全体を 1 つのフィールドに読み込む」— では `open` が設定されません。また、上限のない範囲の min がこれまでに見た最大値以下になるような範囲の順序（範囲は順序に依存しないと文書化されています。例：`new Range(11), new Range(1, 10)`）でも同じ問題が起こります。その結果、開放範囲が行の残りを吸収するはずなのに、strict モードでは、より長い行が `IncorrectLineLengthException` で失敗します。

**環境**
Spring Batch `main` の `cb69762`（6.0.x）。5.x でも再現可能。JDK 21。

**再現手順**
```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setColumns(new Range(1));
tokenizer.tokenize("H1        12345678       1234567890");
// IncorrectLineLengthException: Line is longer than max range 1
```

**期待される動作**
文書化されているとおり、他の範囲に対する上限のない範囲の min の位置に関係なく、開放範囲が行の残りを吸収します。修正とテストを含む PR を提出する予定です。
