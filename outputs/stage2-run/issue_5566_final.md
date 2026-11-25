# Issue #5566 要約: `BatchObservabilityBeanPostProcessor` が手動設定の `ObservationRegistry` を上書きする問題の修正

## 概要
`JobBuilder` / `StepBuilder` で Job・Step ごとに設定した `ObservationRegistry` が、コンテキスト内に `ObservationRegistry` Bean があると `BatchObservabilityBeanPostProcessor` に無条件で上書きされる bug を修正しました。修正後は、registry が未設定の Job / Step / ジョブオペレータ (`TaskExecutorJobOperator`) にのみ Bean の registry が設定されます。Issue は closed、マイルストーンは 6.1.0-RC1 です。

## 問題
- 再現条件: `ObservationRegistry` 型の Bean を定義したうえで、Job（または Step）に別の registry を `observationRegistry(...)` で設定する。
- 症状: 手動で設定した registry ではなく、Bean の registry が使われる。報告時の環境は Spring Batch 5.0+ と記載されています。
- 原因（差分からの読み取り）: `BatchObservabilityBeanPostProcessor` が、既存の設定を確認せず registry を設定していました。

## 修正内容
1. **`BatchObservabilityBeanPostProcessor`**: registry が未設定の Job / Step / ジョブオペレータにだけ Bean の registry を設定し、手動設定を上書きしません。複数 Bean があり `@Primary` がない場合は、何も設定せず警告を1回だけ出します。
2. **未設定状態の保持**: Job / Step / ジョブオペレータは、registry が未設定であることを保持するようになりました（従来は NOOP で補完）。未設定の場合、observation は作られません。`setObservationRegistry` に null を渡すと例外になります。
3. **`DefaultBatchConfiguration#getObservationRegistry()`**: 一意な `ObservationRegistry` Bean があればそれを、なければ NOOP を返します。
4. Javadoc と `micrometer.adoc`（「Choosing the observation registry」節）を更新。
5. テスト: 手動設定の維持、NOOP、複数 Bean、`@Primary` を検証するテストを追加。

### 挙動の変化
| ケース | 修正後 |
|---|---|
| Job / Step に registry を手動設定 | 設定した registry を維持 |
| 明示的に `ObservationRegistry.NOOP` を設定 | 維持される（明示的な無効化として扱う） |
| 未設定 + 一意（または `@Primary`）の Bean あり | Bean の registry を使用 |
| 未設定 + 複数 Bean で `@Primary` なし | 警告を出力し、NOOP 相当（observation が作られない）。明示設定した artifact のみ observe される |
| 未設定 + Bean なし | NOOP 相当（observation が作られない） |

## 利用者への影響・対応
- Job / Step に個別の registry を設定していたのに Bean の registry が使われていた構成では、設定した registry が使われるようになります。
- `ObservationRegistry` Bean を複数定義している場合は、デフォルトで使うものに `@Primary` を付けてください。付けないと未設定の artifact は NOOP 相当になります。
- 特定の Job / Step で observation を無効にしたい場合は `ObservationRegistry.NOOP` を明示的に設定します。
- `setObservationRegistry` に null を渡すと例外になります。
- ジョブオペレータの registry は `@EnableBatchProcessing` の `observationRegistryRef` か、`DefaultBatchConfiguration` の `getObservationRegistry()` のオーバーライドで選択できます。
- `EnableBatchProcessing` / `DefaultBatchConfiguration` を使わない場合は、従来どおり `BatchObservabilityBeanPostProcessor` の登録が必要です。

## 補足
- 修正のリリースバージョン、5.x 系へのバックポートの有無は入力からは不明です。報告時の「5.0+」は環境の記載で、修正が 5.x に入るかは判断できません。
- 従来は `afterPropertiesSet()` で NOOP が補完されていたため、「未設定」と「明示的な NOOP」を区別しにくかった可能性があります（差分からの推測）。
- 再現用の gist / リポジトリの中身は入力になく、差分のテストが報告例（`JobObservationRegistry` / `StepObservationRegistry`）と同一かは確認できません。
- 参照: https://github.com/spring-projects/spring-batch/issues/5566 、https://github.com/spring-projects/spring-batch/commit/e9ec6704b8e71bb26d6318624584475be9807e65
