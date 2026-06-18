import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone

from .forms import (
    CsvImportForm,
    DocumentGenerationForm,
    DuplicateReviewForm,
    PaymentCompletionForm,
    PaymentConfirmationForm,
    PaymentRecordEditForm,
    ProcessingErrorUpdateForm,
)
from .models import (
    GeneratedDocument,
    ImportBatch,
    PaymentRecord,
    ProcessingError,
    WorkLog,
)
from .services.document_generator import (
    generate_payment_notice,
)

CSV_TEMPLATE_COLUMNS = (
    "発行番号",
    "会社名",
    "住所",
    "事業者登録番号",
    "支払金額",
    "支払日",
    "内訳",
    "キャンペーン名",
    "キャンペーン区分",
    "税区分",
    "備考",
)


CSV_TEMPLATE_SAMPLE_ROW = (
    "SAMPLE-2026-001",
    "株式会社テンプレート確認用",
    "福岡県福岡市博多区〇〇9-9-9",
    "T9000000000001",
    "12345",
    "2026-12-31",
    "CSVテンプレート入力例",
    "テンプレート確認キャンペーン",
    "通常キャンペーン",
    "税率10％",
    "入力例です",
)


REQUIRED_COLUMNS = {
    "発行番号",
    "会社名",
    "住所",
    "支払金額",
    "支払日",
    "内訳",
    "税区分",
}

TAX_TYPE_MAP = {
    "税率10％": PaymentRecord.TaxType.TAXABLE_10,
    "税率10%": PaymentRecord.TaxType.TAXABLE_10,
    "税考慮なし": PaymentRecord.TaxType.NON_TAXABLE,
    "要確認": PaymentRecord.TaxType.NEEDS_CONFIRMATION,
}


class CsvEncodingError(Exception):
    """対応していない文字コードのCSVが指定された場合の例外。"""


def decode_uploaded_csv(uploaded_file):
    """UTF-8またはCP932のCSVを文字列へ変換する。"""

    raw_data = uploaded_file.read()

    for encoding in (
        "utf-8-sig",
        "cp932",
    ):
        try:
            decoded_text = raw_data.decode(
                encoding
            )
            return decoded_text, encoding

        except UnicodeDecodeError:
            continue

    raise CsvEncodingError(
        "CSVの文字コードを読み取れませんでした。"
    )

def parse_payment_amount(value):
    """カンマや円表記を除去し、支払金額をDecimalへ変換する。"""

    normalized_value = (
        value.replace(",", "")
        .replace("円", "")
        .strip()
    )

    try:
        amount = Decimal(normalized_value)
    except InvalidOperation as exc:
        raise ValueError(
            "支払金額を数値として認識できません。"
        ) from exc

    if amount < 0:
        raise ValueError(
            "支払金額には0以上の値を指定してください。"
        )

    return amount


def parse_payment_date(value):
    """複数の日付形式を受け付け、date型へ変換する。"""

    date_formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
    )

    for date_format in date_formats:
        try:
            return datetime.strptime(
                value,
                date_format,
            ).date()
        except ValueError:
            continue

    raise ValueError(
        "支払日はYYYY-MM-DDまたはYYYY/MM/DDで入力してください。"
    )


def create_import_error(
    *,
    import_batch,
    source_row_number,
    error_type,
    error_message,
    target_field="",
    error_value="",
):
    """CSV取込時のエラーを記録する。"""

    ProcessingError.objects.create(
        import_batch=import_batch,
        source_row_number=source_row_number,
        error_type=error_type,
        error_message=error_message,
        target_field=target_field,
        error_value=error_value,
    )


def home(request):
    """トップページ兼簡易ダッシュボードを表示する。"""

    context = {
        "total_count": PaymentRecord.objects.count(),
        "imported_count": PaymentRecord.objects.filter(
            status=PaymentRecord.Status.IMPORTED,
        ).count(),
        "waiting_count": PaymentRecord.objects.filter(
            status=PaymentRecord.Status.WAITING_CONFIRMATION,
        ).count(),
        "correction_required_count": PaymentRecord.objects.filter(
            status=PaymentRecord.Status.CORRECTION_REQUIRED,
        ).count(),
        "confirmed_count": PaymentRecord.objects.filter(
            status=PaymentRecord.Status.CONFIRMED,
        ).count(),
        "error_count": ProcessingError.objects.filter(
            resolution_status__in=[
                ProcessingError.ResolutionStatus.UNRESOLVED,
                ProcessingError.ResolutionStatus.IN_PROGRESS,
             ],
        ).count(),
        "completed_count": PaymentRecord.objects.filter(
            status=PaymentRecord.Status.COMPLETED,
        ).count(),
    }

    return render(
        request,
        "payments/home.html",
        context,
    )


def payment_record_list(request):
    """支払対象データを一覧表示する。"""

    payment_records = (
        PaymentRecord.objects
        .select_related(
            "import_batch",
            "created_by",
            "checked_by",
        )
        .all()
    )

    status = request.GET.get(
        "status",
        "",
    ).strip()

    status_choices = dict(
        PaymentRecord.Status.choices
    )

    if status in status_choices:
        payment_records = payment_records.filter(
            status=status,
        )
        current_status_label = status_choices[status]
    else:
        status = ""
        current_status_label = ""

    context = {
        "payment_records": payment_records,
        "current_status": status,
        "current_status_label": current_status_label,
    }

    return render(
        request,
        "payments/payment_record_list.html",
        context,
    )


def import_payment_records(request):
    """CSVから支払対象データを取り込む。"""

    if request.method == "POST":
        form = CsvImportForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            uploaded_file = form.cleaned_data["csv_file"]
            imported_by = form.cleaned_data["imported_by"]

            import_batch = ImportBatch.objects.create(
                file_name=uploaded_file.name,
                imported_by=imported_by,
                status=ImportBatch.Status.PROCESSING,
            )

            total_count = 0
            success_count = 0
            warning_count = 0
            error_count = 0

            try:
                decoded_text, used_encoding = (
                    decode_uploaded_csv(uploaded_file)
                )

                reader = csv.DictReader(
                    io.StringIO(decoded_text)
                )

                csv_columns = set(
                    reader.fieldnames or []
                )

                missing_columns = (
                    REQUIRED_COLUMNS - csv_columns
                )

                if missing_columns:
                    missing_text = "、".join(
                        sorted(missing_columns)
                    )

                    create_import_error(
                        import_batch=import_batch,
                        source_row_number=None,
                        error_type=(
                            ProcessingError
                            .ErrorType
                            .INVALID_FORMAT
                        ),
                        error_message=(
                            f"必要な列が不足しています："
                            f"{missing_text}"
                        ),
                    )

                    import_batch.status = (
                        ImportBatch.Status.FAILED
                    )
                    import_batch.error_count = 1
                    import_batch.save(
                        update_fields=[
                            "status",
                            "error_count",
                            "updated_at",
                        ],
                    )

                    messages.error(
                        request,
                        (
                            "CSVに必要な列が不足しています："
                            f"{missing_text}"
                        ),
                    )

                    return redirect(
                        "payments:import_payment_records"
                    )

                for source_row_number, row in enumerate(
                    reader,
                    start=2,
                ):
                    total_count += 1
                    row_errors = []

                    cleaned_row = {
                        key: (row.get(key) or "").strip()
                        for key in csv_columns
                    }

                    for column_name in REQUIRED_COLUMNS:
                        if not cleaned_row.get(column_name):
                            row_errors.append(
                                {
                                    "type": (
                                        ProcessingError
                                        .ErrorType
                                        .REQUIRED_FIELD_MISSING
                                    ),
                                    "message": (
                                        f"{column_name}が"
                                        "入力されていません。"
                                    ),
                                    "field": column_name,
                                    "value": "",
                                }
                            )

                    payment_amount = None
                    payment_date = None
                    tax_type = None

                    if cleaned_row.get("支払金額"):
                        try:
                            payment_amount = (
                                parse_payment_amount(
                                    cleaned_row["支払金額"]
                                )
                            )
                        except ValueError as exc:
                            row_errors.append(
                                {
                                    "type": (
                                        ProcessingError
                                        .ErrorType
                                        .INVALID_FORMAT
                                    ),
                                    "message": str(exc),
                                    "field": "支払金額",
                                    "value": cleaned_row[
                                        "支払金額"
                                    ],
                                }
                            )

                    if cleaned_row.get("支払日"):
                        try:
                            payment_date = (
                                parse_payment_date(
                                    cleaned_row["支払日"]
                                )
                            )
                        except ValueError as exc:
                            row_errors.append(
                                {
                                    "type": (
                                        ProcessingError
                                        .ErrorType
                                        .INVALID_FORMAT
                                    ),
                                    "message": str(exc),
                                    "field": "支払日",
                                    "value": cleaned_row[
                                        "支払日"
                                    ],
                                }
                            )

                    if cleaned_row.get("税区分"):
                        tax_type = TAX_TYPE_MAP.get(
                            cleaned_row["税区分"]
                        )

                        if tax_type is None:
                            row_errors.append(
                                {
                                    "type": (
                                        ProcessingError
                                        .ErrorType
                                        .INVALID_TAX_TYPE
                                    ),
                                    "message": (
                                        "税区分が想定した値では"
                                        "ありません。"
                                    ),
                                    "field": "税区分",
                                    "value": cleaned_row[
                                        "税区分"
                                    ],
                                }
                            )

                    registration_number = cleaned_row.get(
                        "事業者登録番号",
                        "",
                    )

                    if (
                        registration_number
                        and not re.fullmatch(
                            r"T\d{13}",
                            registration_number,
                        )
                    ):
                        row_errors.append(
                            {
                                "type": (
                                    ProcessingError
                                    .ErrorType
                                    .INVALID_FORMAT
                                ),
                                "message": (
                                    "事業者登録番号は"
                                    "Tと13桁の数字で"
                                    "入力してください。"
                                ),
                                "field": "事業者登録番号",
                                "value": registration_number,
                            }
                        )

                    issue_number = cleaned_row.get(
                        "発行番号",
                        "",
                    )

                    if (
                        issue_number
                        and PaymentRecord.objects.filter(
                            issue_number=issue_number,
                        ).exists()
                    ):
                        row_errors.append(
                            {
                                "type": (
                                    ProcessingError
                                    .ErrorType
                                    .DUPLICATE_ISSUE_NUMBER
                                ),
                                "message": (
                                    "同じ発行番号が"
                                    "すでに登録されています。"
                                ),
                                "field": "発行番号",
                                "value": issue_number,
                            }
                        )

                    if row_errors:
                        error_count += 1

                        for row_error in row_errors:
                            create_import_error(
                                import_batch=import_batch,
                                source_row_number=(
                                    source_row_number
                                ),
                                error_type=row_error["type"],
                                error_message=(
                                    row_error["message"]
                                ),
                                target_field=(
                                    row_error["field"]
                                ),
                                error_value=(
                                    row_error["value"]
                                ),
                            )

                        continue

                    company_name = cleaned_row["会社名"]

                    has_duplicate_warning = (
                        PaymentRecord.objects.filter(
                            company_name=company_name,
                            payment_amount=payment_amount,
                            payment_date=payment_date,
                        ).exists()
                    )

                    if has_duplicate_warning:
                        warning_count += 1
                        duplicate_check_result = (
                            PaymentRecord
                            .DuplicateCheckResult
                            .UNCHECKED
                        )
                    else:
                        success_count += 1
                        duplicate_check_result = (
                            PaymentRecord
                            .DuplicateCheckResult
                            .NOT_DUPLICATE
                        )

                    payment_record = (
                        PaymentRecord.objects.create(
                            import_batch=import_batch,
                            source_row_number=(
                                source_row_number
                            ),
                            issue_number=issue_number,
                            company_name=company_name,
                            address=cleaned_row["住所"],
                            registration_number=(
                                registration_number
                            ),
                            payment_amount=payment_amount,
                            payment_date=payment_date,
                            description=cleaned_row["内訳"],
                            campaign_name=cleaned_row.get(
                                "キャンペーン名",
                                "",
                            ),
                            campaign_type=cleaned_row.get(
                                "キャンペーン区分",
                                "",
                            ),
                            tax_type=tax_type,
                            tax_rate=(
                                Decimal("10")
                                if tax_type
                                == PaymentRecord
                                .TaxType
                                .TAXABLE_10
                                else None
                            ),
                            notes=cleaned_row.get(
                                "備考",
                                "",
                            ),
                            status=(
                                PaymentRecord
                                .Status
                                .IMPORTED
                            ),
                            has_duplicate_warning=(
                                has_duplicate_warning
                            ),
                            duplicate_check_result=(
                                duplicate_check_result
                            ),
                        )
                    )

                    WorkLog.objects.create(
                        payment_record=payment_record,
                        import_batch=import_batch,
                        operator=imported_by,
                        action_type=(
                            WorkLog.ActionType.IMPORT
                        ),
                        action_detail=(
                            "CSVから支払対象データを"
                            "取り込みました。"
                        ),
                    )

                import_batch.total_count = total_count
                import_batch.success_count = success_count
                import_batch.warning_count = warning_count
                import_batch.error_count = error_count
                import_batch.status = (
                    ImportBatch.Status.COMPLETED
                )
                import_batch.save()

                WorkLog.objects.create(
                    import_batch=import_batch,
                    operator=imported_by,
                    action_type=WorkLog.ActionType.IMPORT,
                    action_detail=(
                        f"CSV取込完了：全{total_count}件、"
                        f"正常{success_count}件、"
                        f"警告{warning_count}件、"
                        f"エラー{error_count}件"
                    ),
                )

                messages.success(
                    request,
                    (
                        f"CSVを取り込みました。"
                        f"正常：{success_count}件、"
                        f"警告：{warning_count}件、"
                        f"エラー：{error_count}件"
                    ),
                )

                return redirect(
                    "payments:payment_record_list"
                )

            except CsvEncodingError:
                import_batch.status = (
                    ImportBatch.Status.FAILED
                )
                import_batch.error_count = 1
                import_batch.save()

                create_import_error(
                    import_batch=import_batch,
                    source_row_number=None,
                    error_type=(
                        ProcessingError
                        .ErrorType
                        .INVALID_FORMAT
                    ),
                    error_message=(
                        "CSVの文字コードを"
                        "読み取れませんでした。"
                    ),
                )

                messages.error(
                    request,
                    (
                        "CSVを読み取れませんでした。"
                        "UTF-8UTF-8またはShift_JIS系（CP932）で保存してください。"
                    ),
                )

    else:
        form = CsvImportForm()

    context = {
        "form": form,
    }

    return render(
        request,
        "payments/import_payment_records.html",
        context,
    )

def payment_record_detail(request, pk):
    """支払対象データの詳細を表示する。"""

    payment_record = get_object_or_404(
        PaymentRecord.objects
        .select_related(
            "import_batch",
            "import_batch__imported_by",
            "created_by",
            "checked_by",
        )
        .prefetch_related(
            "generated_documents",
            "processing_errors",
            "work_logs__operator",
        ),
        pk=pk,
    )

    current_document = (
        payment_record.generated_documents
        .filter(is_current=True)
        .first()
    )

    context = {
        "payment_record": payment_record,
        "current_document": current_document,
        "generation_form": DocumentGenerationForm(),
        "confirmation_form": PaymentConfirmationForm(),
        "completion_form": PaymentCompletionForm(),
        "duplicate_review_form": DuplicateReviewForm(),
    }

    return render(
        request,
        "payments/payment_record_detail.html",
        context,
    )

@require_POST
def generate_payment_document(request, pk):
    """Excel形式の支払通知書を作成する。"""

    payment_record = get_object_or_404(
        PaymentRecord,
        pk=pk,
    )

    form = DocumentGenerationForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "作成担当者を選択してください。",
        )
        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    unresolved_error_exists = (
        payment_record.processing_errors.exclude(
            resolution_status=(
                ProcessingError
                .ResolutionStatus
                .RESOLVED
            ),
        ).exists()
    )

    if unresolved_error_exists:
        messages.error(
            request,
            (
                "未解消のエラーがあるため、"
                "支払通知書を作成できません。"
            ),
        )
        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )
    
    if (
        payment_record.duplicate_check_result
        == PaymentRecord
        .DuplicateCheckResult
        .DUPLICATE
    ):
        messages.error(
            request,
            (
                "重複確定となっているため、"
                "支払通知書を作成できません。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    if (
        payment_record.has_duplicate_warning
        and payment_record.duplicate_check_result
        == PaymentRecord.DuplicateCheckResult.UNCHECKED
    ):
        messages.error(
            request,
            (
                "重複警告が未確認のため、"
                "支払通知書を作成できません。"
            ),
        )
        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    operator = form.cleaned_data["created_by"]

    try:
        generated_document = generate_payment_notice(
            payment_record=payment_record,
            operator=operator,
        )
    except FileNotFoundError as exc:
        messages.error(
            request,
            str(exc),
        )
        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    messages.success(
        request,
        (
            "支払通知書を作成しました。"
            f"ファイル：{generated_document.file_name}"
        ),
    )

    return redirect(
        "payments:payment_record_detail",
        pk=payment_record.pk,
    )

def download_generated_document(request, pk):
    """作成済みの支払通知書をダウンロードする。"""

    generated_document = get_object_or_404(
        GeneratedDocument,
        pk=pk,
    )

    media_root = settings.MEDIA_ROOT.resolve()

    file_path = (
        settings.MEDIA_ROOT
        / Path(generated_document.file_path)
    ).resolve()

    if media_root not in file_path.parents:
        raise Http404(
            "不正なファイルパスです。"
        )

    if not file_path.exists():
        raise Http404(
            "支払通知書ファイルが見つかりません。"
        )

    return FileResponse(
        file_path.open("rb"),
        as_attachment=True,
        filename=generated_document.file_name,
    )

@require_POST
@transaction.atomic
def confirm_payment_record(request, pk):
    """支払通知書の確認結果を登録する。"""

    payment_record = get_object_or_404(
        PaymentRecord.objects.select_related(
            "created_by",
            "import_batch",
        ),
        pk=pk,
    )

    form = PaymentConfirmationForm(request.POST)

    if not form.is_valid():
        error_messages = []

        for field_errors in form.errors.values():
            error_messages.extend(field_errors)

        messages.error(
            request,
            " ".join(error_messages),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    current_document_exists = (
        payment_record.generated_documents.filter(
            is_current=True,
        ).exists()
    )

    if not current_document_exists:
        messages.error(
            request,
            (
                "支払通知書が作成されていないため、"
                "確認結果を登録できません。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    if (
        payment_record.status
        != PaymentRecord.Status.WAITING_CONFIRMATION
    ):
        messages.error(
            request,
            (
                "現在のステータスでは、"
                "確認結果を登録できません。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    checked_by = form.cleaned_data["checked_by"]
    result = form.cleaned_data["result"]
    comment = (
        form.cleaned_data["comment"]
        or ""
    ).strip()

    # 作成者本人による確認を防ぐ
    if (
        payment_record.created_by_id
        and payment_record.created_by_id
        == checked_by.pk
    ):
        messages.error(
            request,
            (
                "作成担当者本人を確認担当者に"
                "指定することはできません。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    old_status = payment_record.status

    payment_record.checked_by = checked_by
    payment_record.checked_at = timezone.now()
    payment_record.confirmation_comment = comment
    payment_record.status = result

    payment_record.save(
        update_fields=[
            "checked_by",
            "checked_at",
            "confirmation_comment",
            "status",
            "updated_at",
        ],
    )

    result_display = (
        payment_record.get_status_display()
    )

    detail_parts = [
        f"確認結果を「{result_display}」で登録しました。"
    ]

    if comment:
        detail_parts.append(
            f"確認内容：{comment}"
        )

    WorkLog.objects.create(
        payment_record=payment_record,
        import_batch=payment_record.import_batch,
        operator=checked_by,
        action_type=WorkLog.ActionType.CONFIRM,
        action_detail=" ".join(detail_parts),
        target_field="status",
        old_value=old_status,
        new_value=result,
    )

    if result == PaymentRecord.Status.CONFIRMED:
        messages.success(
            request,
            "支払通知書を確認済みにしました。",
        )
    else:
        messages.warning(
            request,
            "支払通知書を要修正にしました。",
        )

    return redirect(
        "payments:payment_record_detail",
        pk=payment_record.pk,
    )

def processing_error_list(request):
    """処理エラーを一覧表示する。"""

    processing_errors = (
        ProcessingError.objects
        .select_related(
            "payment_record",
            "import_batch",
            "resolved_by",
        )
        .all()
    )

    status = request.GET.get(
        "status",
        "",
    ).strip()

    status_choices = dict(
        ProcessingError.ResolutionStatus.choices
    )

    if status == "open":
        processing_errors = processing_errors.filter(
            resolution_status__in=[
                ProcessingError
                .ResolutionStatus
                .UNRESOLVED,
                ProcessingError
                .ResolutionStatus
                .IN_PROGRESS,
            ],
        )
        current_status_label = "未対応・対応中"

    elif status in status_choices:
        processing_errors = processing_errors.filter(
            resolution_status=status,
        )
        current_status_label = status_choices[status]

    else:
        status = ""
        current_status_label = ""

    context = {
        "processing_errors": processing_errors,
        "current_status": status,
        "current_status_label": current_status_label,
    }

    return render(
        request,
        "payments/processing_error_list.html",
        context,
    )

def processing_error_detail(request, pk):
    """処理エラーの詳細と対応フォームを表示する。"""

    processing_error = get_object_or_404(
        ProcessingError.objects
        .select_related(
            "payment_record",
            "import_batch",
            "resolved_by",
        ),
        pk=pk,
    )

    update_form = ProcessingErrorUpdateForm(
        initial={
            "resolved_by": (
                processing_error.resolved_by
            ),
            "resolution_status": (
                processing_error.resolution_status
            ),
            "resolution_note": (
                processing_error.resolution_note
            ),
        },
    )

    context = {
        "processing_error": processing_error,
        "update_form": update_form,
    }

    return render(
        request,
        "payments/processing_error_detail.html",
        context,
    )

@require_POST
@transaction.atomic
def update_processing_error(request, pk):
    """処理エラーの対応状況を更新する。"""

    processing_error = get_object_or_404(
        ProcessingError.objects
        .select_related(
            "payment_record",
            "import_batch",
        ),
        pk=pk,
    )

    form = ProcessingErrorUpdateForm(
        request.POST,
    )

    if not form.is_valid():
        error_messages = []

        for field_errors in form.errors.values():
            error_messages.extend(field_errors)

        messages.error(
            request,
            " ".join(error_messages),
        )

        return redirect(
            "payments:processing_error_detail",
            pk=processing_error.pk,
        )

    resolved_by = form.cleaned_data["resolved_by"]
    resolution_status = form.cleaned_data[
        "resolution_status"
    ]
    resolution_note = (
        form.cleaned_data["resolution_note"]
        or ""
    ).strip()

    old_status = processing_error.resolution_status

    processing_error.resolved_by = resolved_by
    processing_error.resolution_status = (
        resolution_status
    )
    processing_error.resolution_note = (
        resolution_note
    )

    if (
        resolution_status
        == ProcessingError
        .ResolutionStatus
        .RESOLVED
    ):
        processing_error.resolved_at = timezone.now()
    else:
        processing_error.resolved_at = None

    processing_error.save(
        update_fields=[
            "resolved_by",
            "resolution_status",
            "resolution_note",
            "resolved_at",
            "updated_at",
        ],
    )

    action_type = (
        WorkLog.ActionType.RESOLVE_ERROR
        if resolution_status
        == ProcessingError.ResolutionStatus.RESOLVED
        else WorkLog.ActionType.CHANGE_STATUS
    )

    WorkLog.objects.create(
        payment_record=(
            processing_error.payment_record
        ),
        import_batch=(
            processing_error.import_batch
        ),
        operator=resolved_by,
        action_type=action_type,
        action_detail=(
            "処理エラーの対応状況を"
            f"「{processing_error.get_resolution_status_display()}」"
            "へ変更しました。"
            f" 対応内容：{resolution_note or '記載なし'}"
        ),
        target_field="resolution_status",
        old_value=old_status,
        new_value=resolution_status,
    )

    if (
        resolution_status
        == ProcessingError
        .ResolutionStatus
        .RESOLVED
    ):
        messages.success(
            request,
            "処理エラーを解消済みにしました。",
        )
    else:
        messages.success(
            request,
            "処理エラーの対応状況を更新しました。",
        )

    return redirect(
        "payments:processing_error_detail",
        pk=processing_error.pk,
    )


@transaction.atomic
def edit_payment_record(request, pk):
    """要修正となった支払対象データを編集する。"""

    payment_record = get_object_or_404(
        PaymentRecord.objects.select_related(
            "import_batch",
        ),
        pk=pk,
    )

    if (
        payment_record.status
        != PaymentRecord.Status.CORRECTION_REQUIRED
    ):
        messages.error(
            request,
            (
                "要修正のデータだけ"
                "編集できます。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    editable_fields = [
        "issue_number",
        "company_name",
        "address",
        "registration_number",
        "payment_amount",
        "payment_date",
        "description",
        "campaign_name",
        "campaign_type",
        "tax_type",
        "notes",
    ]

    old_values = {
        field_name: getattr(
            payment_record,
            field_name,
        )
        for field_name in editable_fields
    }

    if request.method == "POST":
        form = PaymentRecordEditForm(
            request.POST,
            instance=payment_record,
        )

        if form.is_valid():
            edited_by = form.cleaned_data[
                "edited_by"
            ]

            changed_fields = [
                field_name
                for field_name in form.changed_data
                if field_name in editable_fields
            ]

            if not changed_fields:
                messages.info(
                    request,
                    "変更された項目はありません。",
                )

                return redirect(
                    "payments:payment_record_detail",
                    pk=payment_record.pk,
                )

            updated_record = form.save(
                commit=False,
            )

            if (
                updated_record.tax_type
                == PaymentRecord
                .TaxType
                .TAXABLE_10
            ):
                updated_record.tax_rate = Decimal(
                    "10"
                )
            else:
                updated_record.tax_rate = None

            updated_record.save()

            for field_name in changed_fields:
                model_field = (
                    PaymentRecord
                    ._meta
                    .get_field(field_name)
                )

                old_value = old_values[
                    field_name
                ]
                new_value = getattr(
                    updated_record,
                    field_name,
                )

                WorkLog.objects.create(
                    payment_record=updated_record,
                    import_batch=(
                        updated_record.import_batch
                    ),
                    operator=edited_by,
                    action_type=(
                        WorkLog.ActionType.UPDATE
                    ),
                    action_detail=(
                        f"{model_field.verbose_name}"
                        "を修正しました。"
                    ),
                    target_field=field_name,
                    old_value=(
                        ""
                        if old_value is None
                        else str(old_value)
                    ),
                    new_value=(
                        ""
                        if new_value is None
                        else str(new_value)
                    ),
                )

            messages.success(
                request,
                (
                    "支払対象データを修正しました。"
                    "支払通知書を再作成してください。"
                ),
            )

            return redirect(
                "payments:payment_record_detail",
                pk=updated_record.pk,
            )

    else:
        form = PaymentRecordEditForm(
            instance=payment_record,
        )

    context = {
        "payment_record": payment_record,
        "form": form,
    }

    return render(
        request,
        "payments/payment_record_edit.html",
        context,
    )


@require_POST
@transaction.atomic
def complete_payment_record(request, pk):
    """確認済みの支払対象を完了へ変更する。"""

    payment_record = get_object_or_404(
        PaymentRecord.objects.select_related(
            "import_batch",
        ),
        pk=pk,
    )

    form = PaymentCompletionForm(request.POST)

    if not form.is_valid():
        error_messages = []

        for field_errors in form.errors.values():
            error_messages.extend(field_errors)

        messages.error(
            request,
            " ".join(error_messages),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    if (
        payment_record.status
        != PaymentRecord.Status.CONFIRMED
    ):
        messages.error(
            request,
            (
                "確認済みのデータだけ"
                "完了にできます。"
            ),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    completed_by = form.cleaned_data["completed_by"]
    comment = (
        form.cleaned_data["comment"]
        or ""
    ).strip()

    old_status = payment_record.status

    payment_record.status = (
        PaymentRecord.Status.COMPLETED
    )
    payment_record.completed_at = timezone.now()

    payment_record.save(
        update_fields=[
            "status",
            "completed_at",
            "updated_at",
        ],
    )

    detail = "支払対象を完了にしました。"

    if comment:
        detail += f" 完了コメント：{comment}"

    WorkLog.objects.create(
        payment_record=payment_record,
        import_batch=payment_record.import_batch,
        operator=completed_by,
        action_type=WorkLog.ActionType.CHANGE_STATUS,
        action_detail=detail,
        target_field="status",
        old_value=old_status,
        new_value=PaymentRecord.Status.COMPLETED,
    )

    messages.success(
        request,
        "支払対象を完了にしました。",
    )

    return redirect(
        "payments:payment_record_detail",
        pk=payment_record.pk,
    )


@require_POST
@transaction.atomic
def review_duplicate_candidate(request, pk):
    """重複候補について人による確認結果を登録する。"""

    payment_record = get_object_or_404(
        PaymentRecord.objects.select_related(
            "import_batch",
        ),
        pk=pk,
    )

    if not payment_record.has_duplicate_warning:
        messages.error(
            request,
            "この支払対象には重複警告がありません。",
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    if (
        payment_record.duplicate_check_result
        != PaymentRecord
        .DuplicateCheckResult
        .UNCHECKED
    ):
        messages.error(
            request,
            "重複確認結果はすでに登録されています。",
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    form = DuplicateReviewForm(request.POST)

    if not form.is_valid():
        error_messages = []

        for field_errors in form.errors.values():
            error_messages.extend(field_errors)

        messages.error(
            request,
            " ".join(error_messages),
        )

        return redirect(
            "payments:payment_record_detail",
            pk=payment_record.pk,
        )

    reviewed_by = form.cleaned_data["reviewed_by"]
    result = form.cleaned_data["result"]
    comment = form.cleaned_data["comment"].strip()

    old_result = payment_record.duplicate_check_result

    payment_record.duplicate_check_result = result
    payment_record.save(
        update_fields=[
            "duplicate_check_result",
            "updated_at",
        ],
    )

    result_display = (
        payment_record
        .get_duplicate_check_result_display()
    )

    WorkLog.objects.create(
        payment_record=payment_record,
        import_batch=payment_record.import_batch,
        operator=reviewed_by,
        action_type=(
            WorkLog.ActionType.CHECK_DUPLICATE
        ),
        action_detail=(
            f"重複確認結果を「{result_display}」"
            f"で登録しました。判断理由：{comment}"
        ),
        target_field="duplicate_check_result",
        old_value=old_result,
        new_value=result,
    )

    if (
        result
        == PaymentRecord
        .DuplicateCheckResult
        .ALLOWED
    ):
        messages.success(
            request,
            (
                "正当な別支払として登録しました。"
                "支払通知書を作成できます。"
            ),
        )
    else:
        messages.warning(
            request,
            (
                "重複確定として登録しました。"
                "このデータから支払通知書は"
                "作成できません。"
            ),
        )

    return redirect(
        "payments:payment_record_detail",
        pk=payment_record.pk,
    )


def build_payment_csv_template(
    *,
    include_sample=False,
):
    """支払対象CSVテンプレートをレスポンスとして作成する。"""

    if include_sample:
        filename = "payment_import_template_sample.csv"
    else:
        filename = "payment_import_template.csv"

    response = HttpResponse(
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # 日本語版Excelでも文字化けしにくいUTF-8 BOMを付ける
    response.write("\ufeff")

    writer = csv.writer(
        response,
        lineterminator="\r\n",
    )
    writer.writerow(
        CSV_TEMPLATE_COLUMNS
    )

    if include_sample:
        writer.writerow(
            CSV_TEMPLATE_SAMPLE_ROW
        )

    return response


def download_payment_csv_template(request):
    """ヘッダーだけのCSVテンプレートをダウンロードする。"""

    return build_payment_csv_template()


def download_payment_csv_sample(request):
    """入力例付きCSVテンプレートをダウンロードする。"""

    return build_payment_csv_template(
        include_sample=True,
    )