*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

`MultiResourceItemWriter` の `itemCountLimitPerResource`（1つの出力リソース（ファイル）に書き込む最大件数）に 0 や負数を指定しても、エラーになりません。問題は書き込みを始めて初めて表に出ます（[#5597](https://github.com/spring-projects/spring-batch/issues/5597)）。

### 症状（issue の記述）

- `0`: アイテムが1件も書かれないまま次のリソースへ進み続け、処理が完了しません。
- `-1`（負数）: チャンクを分割する範囲の計算が不正になります。

### 再現手順

1. `delegate` と出力リソースを指定して `MultiResourceItemWriter` を設定する
2. `itemCountLimitPerResource` を `0`（または `-1`）に設定する
3. ライターをオープンする
4. 空でないチャンクを書き込む

### 期待される動作

0 以下の上限値は、書き込み開始前の設定時に `IllegalArgumentException` で拒否されるべきです。`setItemCountLimitPerResource` の直接呼び出しと、`MultiResourceItemWriterBuilder.build()` の両方が対象です。

### 業務への影響

issue の症状（0 は正常に完了しない、負数は範囲計算が不正になる）から、0 以下の指定は実質的に使えない設定でした。修正後は、書き込み時ではなく `setItemCountLimitPerResource` の呼び出し時（Bean 生成時など）に例外で失敗します。

アップグレード時は、`itemCountLimitPerResource` を XML や Java Config のほか、外部プロパティやジョブパラメータから渡している場合に、値が 1 以上になっているかを確認してください。

## 原因

`itemCountLimitPerResource` の値に対する妥当性検証が無かったことです。0 や負数がそのまま受け入れられていました。挙動の詳細は、上記の症状（issue の報告）を参照してください。

- 0 の場合: issue では、書き込み件数が 0 のまま上限到達と判定され、リソース切替が繰り返されると説明されています。
- 負数の場合: issue では、範囲計算が不正になり、不正なサブリスト範囲が発生すると説明されています。

## 対応方針

修正コミット [624eadb7dae3](https://github.com/spring-projects/spring-batch/commit/624eadb7dae3023fb0d0809e2a01590321f94d4a) の diff に含まれる本体コードの修正は `setItemCountLimitPerResource` のみで、`MultiResourceItemWriterBuilder` 側のコード変更はありません。`build()` 経由で例外になることは、追加テストの期待としてのみ確認できます。builder が内部で setter を呼ぶかどうかは、入力からは確認できません。

- `setItemCountLimitPerResource` に 1 未満を渡すと `IllegalArgumentException` になります。失敗が書き込み時から設定時へ前倒しされます。
- `0` と `-1` のパラメータ化テストが追加され、setter と `build()` の両方が `IllegalArgumentException` をスローすることを検証しています。終了しない書き込みループ自体は、テストで実行していません。

## バグの発生タイミング

導入バージョン・コミットは、入力からは特定できません。ラベルによると、6.1.0-RC1 で修正され、6.0.x へのバックポートが予定されています（`for: backport-to-6.0.x`）。修正コミットは [624eadb7dae3](https://github.com/spring-projects/spring-batch/commit/624eadb7dae3023fb0d0809e2a01590321f94d4a) です。
