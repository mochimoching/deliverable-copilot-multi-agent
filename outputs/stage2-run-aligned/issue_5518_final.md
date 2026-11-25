*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

`FixedLengthTokenizer` で strict が有効なとき、開放範囲を含む設定でも、行が長いと `IncorrectLineLengthException` が出る不具合です（[#5518](https://github.com/spring-projects/spring-batch/issues/5518)）。`Range` は固定長ファイルの列範囲で、開放範囲（max のない `Range`、例: `new Range(1)`）を指定すると、`setColumns` の Javadoc では「行の残りがその列に読み込まれる（strict の設定に関係なく）」とされています。strict は `setStrict` で設定します。

- `setColumns(new Range(1))`（行全体を1フィールドに）: 修正前は長い行で `IncorrectLineLengthException` になっていました。修正後は行全体が1フィールドに読み込まれます。
- `setColumns(new Range(11), new Range(1, 10))`（開放範囲を先頭に書いた順序）: 修正前は長い行で `IncorrectLineLengthException` になっていました。修正後は1〜10桁目と11桁目以降の2フィールドに分割されます。

再現コード（issue より）:

```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setColumns(new Range(1));
tokenizer.tokenize("H1        12345678       1234567890");
// IncorrectLineLengthException: Line is longer than max range 1
```

**アップグレード時の注意**: `FixedLengthTokenizer` を strict 有効で使い、`Range` に開放範囲を含めている場合、長い行の読み込み結果が変わります。たとえば、長い行を `IncorrectLineLengthException` で検知して不正データとしてスキップしていたジョブでは、修正後は検知されなくなります。

## 原因

開放範囲の `min` が、他の範囲の最大値（`maxRange`）より大きいときだけ開放扱い（`open = true`）にしていたためです。`maxRange` は `ranges[0].getMin()` で初期化されるので、単一の開放範囲などでは判定が外れ、長すぎる行として例外になっていました。

```java
upperBound = range.getMin();
if (upperBound > maxRange) {
    open = true;
}
```

## 対応方針

修正の中身は次の2点です。

- `FixedLengthTokenizer#calculateMaxRange`: 開放範囲が見つかれば、`min` と `maxRange` を比較せず無条件に `open = true` とする。
- `setColumns` の Javadoc を、「最後の範囲が開放なら」から「開放範囲があれば、strict の設定や配列内での位置を問わず行の残りをその列に読み込む」に更新。

`FixedLengthTokenizerTests` に、上記2設定に対応するテスト（`testLongerLinesSingleOpenRange`、`testLongerLinesOpenRangeStartingAtFirstColumnMin`）を追加しています。

issue が指摘した Javadoc と実装のずれを、実装側を直して解消しました。

## バグの発生タイミング

- 報告時点: [cb69762](https://github.com/spring-projects/spring-batch/commit/cb69762) 時点の Spring Batch `main`（6.0.x）。issue では 5.x でも再現するとされています。
- バグを混入させたコミット・バージョン: 入力からは特定できません。
- 修正コミット: [4d9aecb33618](https://github.com/spring-projects/spring-batch/commit/4d9aecb33618cd153e57905069052df2a0d10a44)（マイルストーン 6.1.0-RC1）。
- ラベルに `for: backport-to-6.0.x` がありますが、実際にバックポートされたかは入力からは分かりません。5.x 利用者が修正版を確認する際は、6.0.x のリリースノートを見てください。
