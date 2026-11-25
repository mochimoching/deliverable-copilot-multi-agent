*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# 厳密モードの FixedLengthTokenizer が、開放範囲の開始位置が最初の範囲の min 以下の場合に行を拒否する

**Issue番号**: #5518
**状態**: closed | **作成者**: hunseonglee | **作成日**: 2026-09-03
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5518

## 内容

**バグの説明**
`FixedLengthTokenizer#setColumns` の Javadoc には次のように記載されています。「最後の範囲が開放(open)されている場合、行の残りの部分が(strict フラグの設定に関係なく)その列に読み込まれます。」しかし、`calculateMaxRange` は、上限のない範囲の min が、これまでに見た最大値よりも*厳密に大きい*場合にのみ、トークナイザーを open としてマークします。

```java
upperBound = range.getMin();
if (upperBound > maxRange) {
    open = true;
}
```

`maxRange` は `ranges[0].getMin()` で初期化されるため、単一の開放範囲の列、つまり `setColumns(new Range(1))`(「行全体を1つのフィールドに読み込む」)では `open` が設定されません。また、上限のない範囲の min が、これまでに見た最大値以下になるような範囲の順序(範囲は順序に依存しないとドキュメント化されています。例: `new Range(11), new Range(1, 10)`)でも同じ問題が発生します。その結果、開放範囲が行の残りを吸収するはずであるにもかかわらず、より長い行は strict モードで `IncorrectLineLengthException` により失敗します。

**環境**
`cb69762` 時点の Spring Batch `main`(6.0.x)。5.x でも再現可能です。JDK 21。

**再現手順**
```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setColumns(new Range(1));
tokenizer.tokenize("H1        12345678       1234567890");
// IncorrectLineLengthException: Line is longer than max range 1
```

**期待される動作**
ドキュメントどおり、上限のない範囲の min が他の範囲に対してどこに位置していても、開放範囲が行の残りを吸収します。修正とテストを含む PR を提出する予定です。
