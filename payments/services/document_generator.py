import re
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from payments.models import (
    GeneratedDocument,
    Operator,
    PaymentRecord,
    WorkLog,
)


def sanitize_file_name(value: str) -> str:
    """ファイル名に使用しにくい文字を置き換える。"""

    return re.sub(
        r'[^0-9A-Za-zぁ-んァ-ヶ一-龠_-]',
        "_",
        value,
    )


@transaction.atomic
def generate_payment_notice(
    *,
    payment_record: PaymentRecord,
    operator: Operator,
) -> GeneratedDocument:
    """支払対象データからExcel支払通知書を作成する。"""

    template_path = (
        settings.BASE_DIR
        / "document_templates"
        / "payment_notice_template.xlsx"
    )

    if not template_path.exists():
        raise FileNotFoundError(
            "支払通知書テンプレートが見つかりません。"
        )

    latest_document = (
        payment_record.generated_documents
        .order_by("-version")
        .first()
    )

    next_version = (
        latest_document.version + 1
        if latest_document
        else 1
    )

    safe_issue_number = sanitize_file_name(
        payment_record.issue_number
    )

    file_name = (
        f"{safe_issue_number}_"
        f"v{next_version}.xlsx"
    )

    relative_path = (
        Path("generated_documents")
        / str(payment_record.pk)
        / file_name
    )

    absolute_path = (
        settings.MEDIA_ROOT
        / relative_path
    )

    absolute_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    workbook = load_workbook(template_path)
    worksheet = workbook["支払通知書"]

    # テンプレート仕様v1のセル位置へ反映
    worksheet["C3"] = timezone.localdate()
    worksheet["C4"] = payment_record.issue_number
    worksheet["C6"] = (
        f"{payment_record.company_name} 御中"
    )
    worksheet["C7"] = payment_record.address
    worksheet["C8"] = (
        payment_record.registration_number
        or "未登録"
    )
    worksheet["C13"] = int(
        payment_record.payment_amount
    )
    worksheet["C14"] = payment_record.payment_date
    worksheet["C17"] = payment_record.description
    worksheet["C20"] = (
        payment_record.get_tax_type_display()
    )
    worksheet["C22"] = payment_record.notes or ""

    workbook.save(absolute_path)

    # 以前のファイルを旧版へ変更
    payment_record.generated_documents.filter(
        is_current=True,
    ).update(
        is_current=False,
    )

    generated_document = (
        GeneratedDocument.objects.create(
            payment_record=payment_record,
            file_name=file_name,
            file_path=relative_path.as_posix(),
            file_type=(
                GeneratedDocument.FileType.EXCEL
            ),
            version=next_version,
            is_current=True,
            created_by=operator,
        )
    )

    # 支払対象の状態を更新
    payment_record.created_by = operator
    payment_record.document_created_at = (
        timezone.now()
    )
    payment_record.checked_by = None
    payment_record.checked_at = None
    payment_record.confirmation_comment = ""
    payment_record.completed_at = None
    payment_record.status = (
        PaymentRecord.Status.WAITING_CONFIRMATION
    )
    payment_record.save(
        update_fields=[
            "created_by",
            "document_created_at",
            "checked_by",
            "checked_at",
            "confirmation_comment",
            "completed_at",
            "status",
            "updated_at",
        ]
    )

    action_type = (
        WorkLog.ActionType.REGENERATE_DOCUMENT
        if next_version > 1
        else WorkLog.ActionType.GENERATE_DOCUMENT
    )

    WorkLog.objects.create(
        payment_record=payment_record,
        import_batch=payment_record.import_batch,
        operator=operator,
        action_type=action_type,
        action_detail=(
            "支払通知書を作成しました。"
            f"バージョン：{next_version}"
        ),
    )

    return generated_document