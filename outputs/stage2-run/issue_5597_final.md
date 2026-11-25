# Issue #5597 要約: `MultiResourceItemWriter` が 0 以下の `itemCountLimitPerResource` を検証しない問題

## 概要
`MultiResourceItemWriter` は `itemCountLimitPerResource` に 0 や負数を設定でき、異常は書き込み開始時まで表に出ませんでした。修正により、0 以下の値は設定時に `IllegalArgumentException` で拒否されます（修正コミット 624eadb7dae3、マイルストーン 6.1.0-RC1）。ラベルに `for: backport-to-6.0.x` はありますが、修正の対象は 6.1.0-RC1 であり、6.0.x へのバックポートは未確認です。6.0.x でも修正済みとは限りません。

## 問題
`setItemCountLimitPerResource` と `MultiResourceItemWriterBuilder.build()` のどちらの経路でも、0 や負数が例外なく受け付けられていました。

- 0 の場合: 書き込みが進捗なしのまま終わらなくなります。
- 負数の場合（例: -1）: 書き込み時に不正な sublist 範囲が生じます。

issue では、追加されたテストはこの検証漏れを示すもので、終わらない書き込みループ自体は実行しないと説明されています。

## 修正内容
- `setItemCountLimitPerResource` で 0 以下の値を設定時に拒否するようにしました。
- 同メソッドの Javadoc を更新しました。
- セッター経由とビルダーの `build()` 経由について、0 と -1 を対象にしたテストが追加されています。
- `MultiResourceItemWriterBuilder` 本体のコード変更は差分に含まれていません。

## 利用者への影響・対応
- `itemCountLimitPerResource` に 0 以下を設定していた構成は、書き込み時ではなく設定時に失敗するようになります。
- 設定値（外部化している場合を含む）が 1 以上であることを確認してください。
- 正の値を設定している既存の構成には、この差分からは影響は読み取れません。

## 補足
- ビルダーが内部でセッターを呼んで検証が効いているのかは、差分にビルダー本体がないため推測です。`build()` 向けのテストは追加されていますが、実行結果は入力にないため、確認済みとは言えません。
- 6.0.x へのバックポートが実施済みかどうかは入力に記載がありません。
