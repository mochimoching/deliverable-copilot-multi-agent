# Issue #5518 要約: `FixedLengthTokenizer` の strict モードで開区間 `Range` が行の残りを吸収しない問題
## 概要
`FixedLengthTokenizer` を strict モードで使う場合に、上限のない（開区間の）`Range` が行の残りを読み取らず、`IncorrectLineLengthException` が発生するバグの修正です。Issue #5518（closed、ラベル: `in: infrastructure` / `type: bug` / `for: backport-to-6.0.x`、マイルストーン 6.1.0-RC1）で報告され、コミット 4d9aecb33618 で修正されました。

## 問題
`FixedLengthTokenizer#setColumns` の Javadoc には「最後の範囲が開区間なら、strict フラグに関係なく行の残りがその列に読み込まれる」と書かれています。しかし実際には、`calculateMaxRange` が `upperBound > maxRange` のときだけ `open = true` にしていました。`maxRange` は `ranges[0].getMin()` で初期化されるため、次のような場合に `open` が立ちません。

- `setColumns(new Range(1))` のように、開区間 1 つで「行全体を 1 フィールドに読む」設定
- 開区間の `min` が、それまでに見た最大値以下になる並び（例: `new Range(11), new Range(1, 10)`。`Range` は順序に依存しない仕様）

結果として、行が長いと strict モードで次の例外になります。

```java
tokenizer.setColumns(new Range(1));
tokenizer.tokenize("H1        12345678       1234567890");
// IncorrectLineLengthException: Line is longer than max range 1
```

Issue では main（`cb69762`、6.0.x）で確認され、5.x でも再現するとされています。

## 修正内容
変更は `spring-batch-infrastructure` の 2 ファイルです。

- `FixedLengthTokenizer.java`
  - `calculateMaxRange` で、開区間の `Range` を見つけたら条件なしに `open = true` とするよう変更（`if (upperBound > maxRange)` を削除）。
  - `setColumns` の Javadoc を、「最後の範囲」ではなく「上限のない範囲であれば、配列内の位置や strict 設定に関係なく行の残りを読み込む」という記述に更新。
- `FixedLengthTokenizerTests.java`（テスト追加）
  - `testLongerLinesSingleOpenRange`: `new Range(1)` のみの設定で、長い行全体が 1 フィールドになることを確認。
  - `testLongerLinesOpenRangeStartingAtFirstColumnMin`: `new Range(11), new Range(1, 10)` の順で、2 フィールドに分割されることを確認。

## 利用者への影響・対応
次のような設定で、strict モードの `FixedLengthTokenizer` を使っている場合に影響する可能性があります。

- `new Range(1)` など、開区間のみを指定している
- 開区間を配列の先頭など、最後以外に置いている

修正後は、これらの設定でも長い行が `IncorrectLineLengthException` にならず、開区間の列が残りを受け取ります。該当する設定がある場合は、修正を含むバージョンへ更新した際に動作を確認するとよいでしょう。修正が含まれる具体的なバージョンは、入力からは確認できません（ラベルとマイルストーンから 6.1.0-RC1 と 6.0.x 系へのバックポートが想定されますが、推測です）。

## 補足
- バックポートが実際に行われたか、5.x のどのバージョンが影響を受けるかは、入力からは不明です。
- `calculateMaxRange` の全体像は diff に出ていないため、`maxRange` の更新や strict 判定の後続処理については触れていません。
- 開区間より後ろに別の範囲がある設定で既存挙動が変わるかは、入力からは確認できていません。
- 修正の PR 番号は不明です（Issue 本文には、報告者が PR を出す旨の記載のみあります）。
