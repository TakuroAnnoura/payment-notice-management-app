from django.db import models

# Create your models here.


class Operator(models.Model):
    """支払通知書作成業務を担当するユーザー。"""

    class Role(models.TextChoices):
        MANAGER = "manager", "管理者/SV"
        CREATOR = "creator", "作成担当"
        CHECKER = "checker", "確認担当"

    name = models.CharField(
        "担当者名",
        max_length=100,
    )
    role = models.CharField(
        "役割",
        max_length=20,
        choices=Role.choices,
    )
    is_active = models.BooleanField(
        "有効状態",
        default=True,
    )
    created_at = models.DateTimeField(
        "作成日時",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "更新日時",
        auto_now=True,
    )

    class Meta:
        verbose_name = "担当者"
        verbose_name_plural = "担当者"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.name}（{self.get_role_display()}）"


class ImportBatch(models.Model):
    """CSVファイルを取り込んだ単位を管理する。"""

    class Status(models.TextChoices):
        PROCESSING = "processing", "処理中"
        COMPLETED = "completed", "完了"
        FAILED = "failed", "失敗"

    file_name = models.CharField(
        "取込ファイル名",
        max_length=255,
    )
    imported_by = models.ForeignKey(
        Operator,
        verbose_name="取込担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_batches",
    )
    total_count = models.PositiveIntegerField(
        "全体件数",
        default=0,
    )
    success_count = models.PositiveIntegerField(
        "正常件数",
        default=0,
    )
    warning_count = models.PositiveIntegerField(
        "警告件数",
        default=0,
    )
    error_count = models.PositiveIntegerField(
        "エラー件数",
        default=0,
    )
    status = models.CharField(
        "取込状態",
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    imported_at = models.DateTimeField(
        "取込日時",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "更新日時",
        auto_now=True,
    )

    class Meta:
        verbose_name = "取込履歴"
        verbose_name_plural = "取込履歴"
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.file_name}（{self.imported_at:%Y-%m-%d %H:%M}）"


class PaymentRecord(models.Model):
    """支払対象者情報と処理状況を管理する。"""

    class Status(models.TextChoices):
        IMPORTED = "imported", "取込済み"
        WAITING_CONFIRMATION = "waiting_confirmation", "確認待ち"
        CONFIRMED = "confirmed", "確認済み"
        CORRECTION_REQUIRED = "correction_required", "要修正"
        ERROR = "error", "エラー"
        COMPLETED = "completed", "完了"

    class TaxType(models.TextChoices):
        TAXABLE_10 = "taxable_10", "税率10％"
        NON_TAXABLE = "non_taxable", "税考慮なし"
        NEEDS_CONFIRMATION = "needs_confirmation", "要確認"

    class DuplicateCheckResult(models.TextChoices):
        UNCHECKED = "unchecked", "未確認"
        NOT_DUPLICATE = "not_duplicate", "重複なし"
        DUPLICATE = "duplicate", "重複確定"
        ALLOWED = "allowed", "正当な別支払"

    import_batch = models.ForeignKey(
        ImportBatch,
        verbose_name="取込履歴",
        on_delete=models.PROTECT,
        related_name="payment_records",
    )
    source_row_number = models.PositiveIntegerField(
        "取込元行番号",
    )
    issue_number = models.CharField(
        "発行番号",
        max_length=50,
        db_index=True,
    )
    company_name = models.CharField(
        "会社名",
        max_length=255,
    )
    address = models.TextField(
        "住所",
    )
    registration_number = models.CharField(
        "事業者登録番号",
        max_length=14,
        blank=True,
    )
    payment_amount = models.DecimalField(
        "支払金額",
        max_digits=12,
        decimal_places=0,
    )
    payment_date = models.DateField(
        "支払日",
    )
    description = models.TextField(
        "内訳",
    )
    campaign_name = models.CharField(
        "キャンペーン名",
        max_length=255,
        blank=True,
    )
    campaign_type = models.CharField(
        "キャンペーン区分",
        max_length=100,
        blank=True,
    )
    tax_type = models.CharField(
        "税区分",
        max_length=30,
        choices=TaxType.choices,
    )
    tax_rate = models.DecimalField(
        "税率",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.TextField(
        "備考",
        blank=True,
    )
    status = models.CharField(
        "ステータス",
        max_length=30,
        choices=Status.choices,
        default=Status.IMPORTED,
        db_index=True,
    )
    has_duplicate_warning = models.BooleanField(
        "重複警告",
        default=False,
    )
    duplicate_check_result = models.CharField(
        "重複確認結果",
        max_length=20,
        choices=DuplicateCheckResult.choices,
        default=DuplicateCheckResult.UNCHECKED,
    )
    created_by = models.ForeignKey(
        Operator,
        verbose_name="作成担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_payment_records",
    )
    checked_by = models.ForeignKey(
        Operator,
        verbose_name="確認担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_payment_records",
    )
    document_created_at = models.DateTimeField(
        "通知書作成日時",
        null=True,
        blank=True,
    )
    confirmation_comment = models.TextField(
        "確認コメント",
        blank=True,
        default="",
    )
    checked_at = models.DateTimeField(
        "確認日時",
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        "完了日時",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        "作成日時",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "更新日時",
        auto_now=True,
    )

    class Meta:
        verbose_name = "支払対象"
        verbose_name_plural = "支払対象"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["import_batch", "source_row_number"],
                name="unique_source_row_per_import_batch",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.issue_number}：{self.company_name}"
    
class GeneratedDocument(models.Model):
    """作成した支払通知書ファイルを管理する。"""

    class FileType(models.TextChoices):
        EXCEL = "excel", "Excel"
        PDF = "pdf", "PDF"

    payment_record = models.ForeignKey(
        PaymentRecord,
        verbose_name="支払対象",
        on_delete=models.CASCADE,
        related_name="generated_documents",
    )
    file_name = models.CharField(
        "ファイル名",
        max_length=255,
    )
    file_path = models.CharField(
        "ファイル保存先",
        max_length=500,
    )
    file_type = models.CharField(
        "ファイル形式",
        max_length=20,
        choices=FileType.choices,
        default=FileType.EXCEL,
    )
    version = models.PositiveIntegerField(
        "バージョン",
        default=1,
    )
    is_current = models.BooleanField(
        "現行版",
        default=True,
    )
    created_by = models.ForeignKey(
        Operator,
        verbose_name="作成担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_documents",
    )
    created_at = models.DateTimeField(
        "作成日時",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "作成済み支払通知書"
        verbose_name_plural = "作成済み支払通知書"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_record", "version"],
                name="unique_document_version_per_payment_record",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.payment_record.issue_number} "
            f"version {self.version}"
        )


class ProcessingError(models.Model):
    """取込・作成・確認時に発生したエラーを管理する。"""

    class ErrorType(models.TextChoices):
        REQUIRED_FIELD_MISSING = (
            "required_field_missing",
            "必須項目不足",
        )
        INVALID_FORMAT = (
            "invalid_format",
            "データ形式不正",
        )
        DUPLICATE_ISSUE_NUMBER = (
            "duplicate_issue_number",
            "発行番号重複",
        )
        DUPLICATE_CANDIDATE = (
            "duplicate_candidate",
            "重複候補",
        )
        INVALID_TAX_TYPE = (
            "invalid_tax_type",
            "税区分不正",
        )
        DOCUMENT_GENERATION_ERROR = (
            "document_generation_error",
            "通知書作成エラー",
        )
        CONFIRMATION_MISMATCH = (
            "confirmation_mismatch",
            "確認不一致",
        )
        OTHER = (
            "other",
            "その他",
        )

    class ResolutionStatus(models.TextChoices):
        UNRESOLVED = "unresolved", "未対応"
        IN_PROGRESS = "in_progress", "対応中"
        RESOLVED = "resolved", "解消済み"

    payment_record = models.ForeignKey(
        PaymentRecord,
        verbose_name="支払対象",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processing_errors",
    )
    import_batch = models.ForeignKey(
        ImportBatch,
        verbose_name="取込履歴",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processing_errors",
    )
    source_row_number = models.PositiveIntegerField(
        "取込元行番号",
        null=True,
        blank=True,
    )
    error_type = models.CharField(
        "エラー種別",
        max_length=50,
        choices=ErrorType.choices,
    )
    error_message = models.TextField(
        "エラー内容",
    )
    target_field = models.CharField(
        "対象項目",
        max_length=100,
        blank=True,
    )
    error_value = models.TextField(
        "エラー値",
        blank=True,
    )
    resolution_status = models.CharField(
        "対応状況",
        max_length=20,
        choices=ResolutionStatus.choices,
        default=ResolutionStatus.UNRESOLVED,
    )
    resolution_note = models.TextField(
        "対応内容",
        blank=True,
    )
    resolved_by = models.ForeignKey(
        Operator,
        verbose_name="対応担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_processing_errors",
    )
    occurred_at = models.DateTimeField(
        "発生日時",
        auto_now_add=True,
    )
    resolved_at = models.DateTimeField(
        "解消日時",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        "作成日時",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "更新日時",
        auto_now=True,
    )

    class Meta:
        verbose_name = "処理エラー"
        verbose_name_plural = "処理エラー"
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        if self.payment_record:
            target = self.payment_record.issue_number
        
        elif self.import_batch:
            if self.source_row_number:
                target = (
                    f"{self.import_batch.file_name} "
                    f"{self.source_row_number}行目"
                )
            
            else:
                target = (
                    f"{self.import_batch.file_name} "
                    "ファイル全体"
                )
        
        else:
            target = "対象不明"
        
        return (
            f"{target}："
            f"{self.get_error_type_display()}"
        )
    

class WorkLog(models.Model):
    """担当者による操作履歴を管理する。"""

    class ActionType(models.TextChoices):
        IMPORT = "import", "データ取込"
        UPDATE = "update", "データ修正"
        GENERATE_DOCUMENT = (
            "generate_document",
            "通知書作成",
        )
        REGENERATE_DOCUMENT = (
            "regenerate_document",
            "通知書再作成",
        )
        CONFIRM = "confirm", "確認結果登録"
        CHANGE_STATUS = (
            "change_status",
            "ステータス変更",
        )
        REGISTER_ERROR = (
            "register_error",
            "エラー登録",
        )
        RESOLVE_ERROR = (
            "resolve_error",
            "エラー解消",
        )
        CHECK_DUPLICATE = (
            "check_duplicate",
            "重複確認",
        )

    payment_record = models.ForeignKey(
        PaymentRecord,
        verbose_name="支払対象",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
    )
    import_batch = models.ForeignKey(
        ImportBatch,
        verbose_name="取込履歴",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
    )
    operator = models.ForeignKey(
        Operator,
        verbose_name="操作者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
    )
    action_type = models.CharField(
        "操作種別",
        max_length=50,
        choices=ActionType.choices,
    )
    action_detail = models.TextField(
        "操作内容",
    )
    target_field = models.CharField(
        "対象項目",
        max_length=100,
        blank=True,
    )
    old_value = models.TextField(
        "変更前の値",
        blank=True,
    )
    new_value = models.TextField(
        "変更後の値",
        blank=True,
    )
    created_at = models.DateTimeField(
        "操作日時",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "作業ログ"
        verbose_name_plural = "作業ログ"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"{self.get_action_type_display()} "
            f"（{self.created_at:%Y-%m-%d %H:%M}）"
        )