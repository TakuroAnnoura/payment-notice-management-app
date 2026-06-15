from django.contrib import admin

from .models import (
    GeneratedDocument,
    ImportBatch,
    Operator,
    PaymentRecord,
    ProcessingError,
    WorkLog,
)

# Register your models here.

@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    """担当者の管理画面設定。"""

    list_display = (
        "id",
        "name",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "role",
        "is_active",
    )
    search_fields = ("name",)
    ordering = ("id",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    """取込履歴の管理画面設定。"""

    list_display = (
        "id",
        "file_name",
        "imported_by",
        "total_count",
        "success_count",
        "warning_count",
        "error_count",
        "status",
        "imported_at",
    )
    list_filter = (
        "status",
        "imported_at",
    )
    search_fields = ("file_name",)
    readonly_fields = (
        "imported_at",
        "updated_at",
    )


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    """支払対象の管理画面設定。"""

    list_display = (
        "id",
        "issue_number",
        "company_name",
        "payment_amount",
        "payment_date",
        "tax_type",
        "status",
        "has_duplicate_warning",
        "created_by",
        "checked_by",
    )
    list_filter = (
        "status",
        "tax_type",
        "has_duplicate_warning",
        "duplicate_check_result",
        "payment_date",
    )
    search_fields = (
        "issue_number",
        "company_name",
        "registration_number",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )

@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    """作成済み支払通知書の管理画面設定。"""

    list_display = (
        "id",
        "payment_record",
        "file_name",
        "file_type",
        "version",
        "is_current",
        "created_by",
        "created_at",
    )
    list_filter = (
        "file_type",
        "is_current",
        "created_at",
    )
    search_fields = (
        "file_name",
        "payment_record__issue_number",
        "payment_record__company_name",
    )
    readonly_fields = ("created_at",)


@admin.register(ProcessingError)
class ProcessingErrorAdmin(admin.ModelAdmin):
    """処理エラーの管理画面設定。"""

    list_display = (
        "id",
        "import_batch",
        "source_row_number",
        "payment_record",
        "error_type",
        "target_field",
        "resolution_status",
        "resolved_by",
        "occurred_at",
    )
    list_filter = (
        "error_type",
        "resolution_status",
        "occurred_at",
    )
    search_fields = (
        "payment_record__issue_number",
        "payment_record__company_name",
        "error_message",
    )
    readonly_fields = (
        "occurred_at",
        "created_at",
        "updated_at",
    )


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    """作業ログの管理画面設定。"""

    list_display = (
        "id",
        "payment_record",
        "operator",
        "action_type",
        "target_field",
        "created_at",
    )
    list_filter = (
        "action_type",
        "created_at",
    )
    search_fields = (
        "payment_record__issue_number",
        "payment_record__company_name",
        "operator__name",
        "action_detail",
    )
    readonly_fields = ("created_at",)