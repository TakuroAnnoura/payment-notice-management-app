# データベース設計 v1

## 1. データベース設計の目的

本書では、支払対象者一覧の取込、支払通知書の作成、確認、エラー管理、作業ログ管理に必要なデータ構造を整理する。

初期開発では、MVPの業務フローを実現するために必要なテーブルに絞る。

---

## 2. 初期開発で使用するテーブル

初期開発では、以下の6テーブルを使用する。

| テーブル名               | 用途                       |
| ------------------- | ------------------------ |
| operators           | 管理者/SV、作成担当者、確認担当者を管理する  |
| import_batches      | CSVファイルの取込単位を管理する        |
| payment_records     | 支払対象者と支払通知書作成に必要な情報を管理する |
| generated_documents | 作成した支払通知書ファイルを管理する       |
| errors              | 取込・作成・確認時に発生したエラーを管理する   |
| work_logs           | 操作履歴や修正履歴を管理する           |

---

## 3. テーブル間の関係

```text
operators
   │
   ├──── payment_records
   │        │
   │        ├──── generated_documents
   │        │
   │        ├──── errors
   │        │
   │        └──── work_logs
   │
   └──── work_logs

import_batches
   │
   └──── payment_records
```

関係を文章で表すと、以下のようになる。

* 1回のファイル取込で、複数の支払対象データが作成される
* 1件の支払対象データから、複数の支払通知書ファイルが作成される可能性がある
* 1件の支払対象データに、複数のエラーが登録される可能性がある
* 1件の支払対象データに、複数の作業ログが記録される
* 1人の担当者が、複数の支払対象データや作業ログに関わる

---

# 4. operatorsテーブル

## 4.1 目的

アプリを操作する担当者を管理する。

初期開発ではログイン機能を必須としないため、画面上で担当者を選択するための簡易マスタとして使用する。

## 4.2 項目

| 項目名   | カラム名候補     | 型候補 | 必須 | 内容               |
| ----- | ---------- | --- | -- | ---------------- |
| 担当者ID | id         | 整数  | 必須 | 主キー              |
| 担当者名  | name       | 文字列 | 必須 | 画面に表示する名前        |
| 役割    | role       | 文字列 | 必須 | 管理者/SV、作成担当、確認担当 |
| 有効状態  | is_active  | 真偽値 | 必須 | 現在利用可能な担当者か      |
| 作成日時  | created_at | 日時  | 必須 | 登録日時             |
| 更新日時  | updated_at | 日時  | 必須 | 最終更新日時           |

## 4.3 役割の候補

| 値       | 内容     |
| ------- | ------ |
| manager | 管理者/SV |
| creator | 作成担当   |
| checker | 確認担当   |

1人が複数の役割を持つ可能性はあるが、初期開発では主な役割を1つ設定する簡易方式とする。

---

# 5. import_batchesテーブル

## 5.1 目的

CSVファイルを取り込んだ単位を管理する。

どのファイルから、いつ、何件のデータを取り込んだかを記録する。

## 5.2 項目

| 項目名     | カラム名候補         | 型候補  | 必須 | 内容               |
| ------- | -------------- | ---- | -- | ---------------- |
| 取込ID    | id             | 整数   | 必須 | 主キー              |
| 取込ファイル名 | file_name      | 文字列  | 必須 | 取り込んだCSVファイル名    |
| 保存先     | file_path      | 文字列  | 任意 | 取込ファイルの保存場所      |
| 取込担当者ID | imported_by_id | 外部キー | 任意 | operatorsテーブルを参照 |
| 全体件数    | total_count    | 整数   | 必須 | CSV内のデータ件数       |
| 正常件数    | success_count  | 整数   | 必須 | 正常に取り込んだ件数       |
| 警告件数    | warning_count  | 整数   | 必須 | 警告となった件数         |
| エラー件数   | error_count    | 整数   | 必須 | エラーとなった件数        |
| 取込状態    | status         | 文字列  | 必須 | 処理中、完了、失敗        |
| 取込日時    | imported_at    | 日時   | 必須 | 取込を実行した日時        |
| 作成日時    | created_at     | 日時   | 必須 | レコード作成日時         |
| 更新日時    | updated_at     | 日時   | 必須 | 最終更新日時           |

## 5.3 取込状態

| 値          | 内容    |
| ---------- | ----- |
| processing | 取込処理中 |
| completed  | 取込完了  |
| failed     | 取込失敗  |

---

# 6. payment_recordsテーブル

## 6.1 目的

支払対象者情報、支払通知書作成に必要な情報、現在の作業状況を管理する。

本アプリの中心となるテーブルである。

## 6.2 項目

| 項目名      | カラム名候補                 | 型候補     | 必須 | 内容                    |
| -------- | ---------------------- | ------- | -- | --------------------- |
| 支払対象ID   | id                     | 整数      | 必須 | 主キー                   |
| 取込ID     | import_batch_id        | 外部キー    | 必須 | import_batchesテーブルを参照 |
| 取込元行番号   | source_row_number      | 整数      | 必須 | CSV上の行番号              |
| 発行番号     | issue_number           | 文字列     | 必須 | 支払通知書を識別する番号          |
| 会社名      | company_name           | 文字列     | 必須 | 支払先の会社名               |
| 住所       | address                | 文字列     | 必須 | 支払先の住所                |
| 事業者登録番号  | registration_number    | 文字列     | 任意 | 事業者登録番号               |
| 支払金額     | payment_amount         | Decimal | 必須 | 支払通知書に記載する金額          |
| 支払日      | payment_date           | 日付      | 必須 | 支払予定日または支払日           |
| 内訳       | description            | 文章      | 必須 | キャッシュバック等の内容          |
| キャンペーン名  | campaign_name          | 文字列     | 任意 | 対象キャンペーン名             |
| キャンペーン区分 | campaign_type          | 文字列     | 任意 | キャンペーンの区分             |
| 税区分      | tax_type               | 文字列     | 必須 | 税率10％、税考慮なし、要確認       |
| 税率       | tax_rate               | Decimal | 任意 | 10％などの税率              |
| 備考       | notes                  | 文章      | 任意 | 注意事項や補足               |
| ステータス    | status                 | 文字列     | 必須 | 現在の作業状況               |
| 重複警告     | has_duplicate_warning  | 真偽値     | 必須 | 重複候補があるか              |
| 重複確認結果   | duplicate_check_result | 文字列     | 任意 | 未確認、重複なし、重複確定         |
| 作成担当者ID  | created_by_id          | 外部キー    | 任意 | operatorsテーブルを参照      |
| 確認担当者ID  | checked_by_id          | 外部キー    | 任意 | operatorsテーブルを参照      |
| 通知書作成日時  | document_created_at    | 日時      | 任意 | 支払通知書を作成した日時          |
| 確認日時     | checked_at             | 日時      | 任意 | 確認を完了した日時             |
| 完了日時     | completed_at           | 日時      | 任意 | 業務完了日時                |
| 作成日時     | created_at             | 日時      | 必須 | レコード作成日時              |
| 更新日時     | updated_at             | 日時      | 必須 | 最終更新日時                |

## 6.3 ステータス

MVPでは以下を使用する。

| 値                    | 表示名  | 内容                 |
| -------------------- | ---- | ------------------ |
| imported             | 取込済み | CSVから取り込まれた        |
| waiting_confirmation | 確認待ち | 支払通知書が作成され確認を待っている |
| confirmed            | 確認済み | 確認担当者の確認が完了した      |
| correction_required  | 要修正  | 修正が必要              |
| error                | エラー  | 処理を継続できない問題がある     |
| completed            | 完了   | 作成・確認・修正が完了した      |

「作成済み」と「確認待ち」は初期開発では同じタイミングになるため、MVPでは「確認待ち」にまとめる。

## 6.4 税区分

| 値                  | 表示名   |
| ------------------ | ----- |
| taxable_10         | 税率10％ |
| non_taxable        | 税考慮なし |
| needs_confirmation | 要確認   |

## 6.5 重複確認結果

| 値             | 表示名    |
| ------------- | ------ |
| unchecked     | 未確認    |
| not_duplicate | 重複なし   |
| duplicate     | 重複確定   |
| allowed       | 正当な別支払 |

---

# 7. generated_documentsテーブル

## 7.1 目的

作成された支払通知書ファイルを管理する。

修正後に再作成した場合でも、過去のファイルを上書きせず、バージョンを分けて管理する。

## 7.2 項目

| 項目名     | カラム名候補            | 型候補  | 必須 | 内容                     |
| ------- | ----------------- | ---- | -- | ---------------------- |
| ファイルID  | id                | 整数   | 必須 | 主キー                    |
| 支払対象ID  | payment_record_id | 外部キー | 必須 | payment_recordsテーブルを参照 |
| ファイル名   | file_name         | 文字列  | 必須 | 作成したファイル名              |
| 保存先     | file_path         | 文字列  | 必須 | ファイルの保存場所              |
| ファイル形式  | file_type         | 文字列  | 必須 | ExcelまたはPDF            |
| バージョン   | version           | 整数   | 必須 | 作成ファイルの版数              |
| 現行版     | is_current        | 真偽値  | 必須 | 現在使用するファイルか            |
| 作成担当者ID | created_by_id     | 外部キー | 任意 | operatorsテーブルを参照       |
| 作成日時    | created_at        | 日時   | 必須 | ファイル作成日時               |

## 7.3 バージョン管理例

```text
発行番号：CB-2026-001

version 1
    初回作成
    is_current = false

version 2
    修正後に再作成
    is_current = true
```

1件の支払対象データに対して、現行版となるファイルは1件だけとする。

---

# 8. errorsテーブル

## 8.1 目的

データ取込、支払通知書作成、確認時に発生したエラーを管理する。

1件の支払対象データに対して、複数のエラーを登録できる。

## 8.2 項目

| 項目名     | カラム名候補            | 型候補  | 必須 | 内容                     |
| ------- | ----------------- | ---- | -- | ---------------------- |
| エラーID   | id                | 整数   | 必須 | 主キー                    |
| 支払対象ID  | payment_record_id | 外部キー | 必須 | payment_recordsテーブルを参照 |
| エラー種別   | error_type        | 文字列  | 必須 | 必須不足、形式不正、重複など         |
| エラー内容   | error_message     | 文章   | 必須 | 発生した問題の詳細              |
| 対象項目    | target_field      | 文字列  | 任意 | 問題が発生した項目              |
| エラー値    | error_value       | 文字列  | 任意 | 問題となった入力値              |
| 対応状況    | resolution_status | 文字列  | 必須 | 未対応、対応中、解消済み           |
| 対応内容    | resolution_note   | 文章   | 任意 | 修正内容や確認結果              |
| 対応担当者ID | resolved_by_id    | 外部キー | 任意 | operatorsテーブルを参照       |
| 発生日時    | occurred_at       | 日時   | 必須 | エラー発生日時                |
| 解消日時    | resolved_at       | 日時   | 任意 | エラー解消日時                |
| 作成日時    | created_at        | 日時   | 必須 | レコード作成日時               |
| 更新日時    | updated_at        | 日時   | 必須 | 最終更新日時                 |

## 8.3 エラー種別

| 値                         | 表示名      |
| ------------------------- | -------- |
| required_field_missing    | 必須項目不足   |
| invalid_format            | データ形式不正  |
| duplicate_issue_number    | 発行番号重複   |
| duplicate_candidate       | 重複候補     |
| invalid_tax_type          | 税区分不正    |
| document_generation_error | 通知書作成エラー |
| confirmation_mismatch     | 確認不一致    |
| other                     | その他      |

## 8.4 対応状況

| 値           | 表示名  |
| ----------- | ---- |
| unresolved  | 未対応  |
| in_progress | 対応中  |
| resolved    | 解消済み |

---

# 9. work_logsテーブル

## 9.1 目的

誰が、いつ、どのデータに対して、どのような操作を行ったかを記録する。

データ修正時は、変更前と変更後の値も記録する。

## 9.2 項目

| 項目名    | カラム名候補            | 型候補  | 必須 | 内容                     |
| ------ | ----------------- | ---- | -- | ---------------------- |
| ログID   | id                | 整数   | 必須 | 主キー                    |
| 支払対象ID | payment_record_id | 外部キー | 任意 | payment_recordsテーブルを参照 |
| 取込ID   | import_batch_id   | 外部キー | 任意 | import_batchesテーブルを参照  |
| 操作者ID  | operator_id       | 外部キー | 任意 | operatorsテーブルを参照       |
| 操作種別   | action_type       | 文字列  | 必須 | 取込、作成、確認、修正など          |
| 操作内容   | action_detail     | 文章   | 必須 | 実行した操作の説明              |
| 対象項目   | target_field      | 文字列  | 任意 | 変更対象となった項目             |
| 変更前の値  | old_value         | 文章   | 任意 | 修正前の値                  |
| 変更後の値  | new_value         | 文章   | 任意 | 修正後の値                  |
| 操作日時   | created_at        | 日時   | 必須 | 操作を実行した日時              |

## 9.3 操作種別

| 値                   | 表示名     |
| ------------------- | ------- |
| import              | データ取込   |
| update              | データ修正   |
| generate_document   | 通知書作成   |
| regenerate_document | 通知書再作成  |
| confirm             | 確認結果登録  |
| change_status       | ステータス変更 |
| register_error      | エラー登録   |
| resolve_error       | エラー解消   |
| check_duplicate     | 重複確認    |

---

# 10. 主キーと外部キー

## 10.1 主キー

各テーブルの `id` を主キーとする。

主キーは、アプリ内部で各データを一意に識別するために使用する。

## 10.2 外部キー

| テーブル                | 外部キー              | 参照先                |
| ------------------- | ----------------- | ------------------ |
| import_batches      | imported_by_id    | operators.id       |
| payment_records     | import_batch_id   | import_batches.id  |
| payment_records     | created_by_id     | operators.id       |
| payment_records     | checked_by_id     | operators.id       |
| generated_documents | payment_record_id | payment_records.id |
| generated_documents | created_by_id     | operators.id       |
| errors              | payment_record_id | payment_records.id |
| errors              | resolved_by_id    | operators.id       |
| work_logs           | payment_record_id | payment_records.id |
| work_logs           | import_batch_id   | import_batches.id  |
| work_logs           | operator_id       | operators.id       |

---

# 11. 一意制約

初期開発では、以下の一意制約を設定する。

## 11.1 発行番号

`payment_records.issue_number` は重複を許可しない。

同じ発行番号がすでに存在する場合は、新規登録を停止し、重複エラーとして扱う。

## 11.2 支払通知書のバージョン

`generated_documents` では、以下の組み合わせを重複不可とする。

```text
payment_record_id + version
```

同一の支払対象データで、同じバージョン番号を複数登録しない。

---

# 12. 削除方針

業務履歴を残すため、初期開発ではデータを物理的に削除する機能は原則として作成しない。

誤って取り込んだデータなどは、以下のような状態で管理することを検討する。

* 無効
* 取込取消
* 対象外

MVPでは削除機能を実装する場合でも、関連する作業ログやエラー履歴が失われないようにする。

---

# 13. MVPでは別テーブルにしないデータ

以下の情報は、将来的には別テーブルとして管理できるが、MVPでは `payment_records` に直接保存する。

## 13.1 キャンペーン情報

* キャンペーン名
* キャンペーン区分
* 税区分

将来的に複数の支払対象データで同じキャンペーンを管理する場合は、`campaigns` テーブルとして分離する。

## 13.2 ステータス

MVPでは固定の選択肢としてプログラム内に定義する。

将来的に管理画面からステータスを追加・変更する場合は、ステータスマスタの作成を検討する。

## 13.3 税区分

MVPでは固定の選択肢としてプログラム内に定義する。

---

# 14. MVPの最小構成

MVPの最小構成として特に重要なテーブルは、以下の5つとする。

1. operators
2. payment_records
3. generated_documents
4. errors
5. work_logs

`import_batches` は、CSVファイル単位の履歴管理や取込件数の表示に使用する。

開発量が大きくなった場合でも、取込元ファイル名と行番号は `payment_records` に残し、データの出所を追跡できるようにする。

---

# 15. ER図の簡易表現

```text
operators
  id PK
  name
  role
       │
       │ 1
       │
       ├───────────────┐
       │               │
       ▼               ▼
payment_records      work_logs
  id PK                id PK
  import_batch_id FK   payment_record_id FK
  created_by_id FK     operator_id FK
  checked_by_id FK
       │
       ├──────────────┬───────────────┐
       │ 1            │ 1             │ 1
       ▼              ▼               ▼
generated_documents  errors          work_logs
  payment_record_id   payment_record_id payment_record_id
       ▲
       │
       │ 多
       │
import_batches
  id PK
```

正確なER図は、テーブル設計確定後に図として作成する。

---

# 16. 今後決定すること

実装開始前またはDjangoモデル作成時に、以下を決定する。

* データベースにSQLiteを使用するか
* 支払通知書をExcelまたはPDFのどちらで出力するか
* 取込元CSVファイルを保存するか
* 作成した支払通知書をアプリ内に保存するか
* 発行番号をCSVから受け取るか、アプリ側で採番するか
* 事業者登録番号を必須にするか
* 支払金額に税込・税抜のどちらを保存するか
* 作成担当者と確認担当者を別人にする制約を設けるか
* エラー解消時にステータスを自動で戻すか
* 再作成ファイルの旧バージョンを画面に表示するか
