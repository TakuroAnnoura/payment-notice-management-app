import re

from django import forms
from django.core.validators import FileExtensionValidator

from .models import (
    Operator,
    PaymentRecord,
    ProcessingError,
)

class CsvImportForm(forms.Form):
    """支払対象CSVを取り込むためのフォーム。"""

    imported_by = forms.ModelChoiceField(
        label="取込担当者",
        queryset=Operator.objects.none(),
        empty_label="担当者を選択してください",
    )
    csv_file = forms.FileField(
        label="CSVファイル",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["csv"],
            ),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["imported_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role__in=[
                    Operator.Role.MANAGER,
                    Operator.Role.CREATOR,
                ],
            ).order_by("id")
        )

class DocumentGenerationForm(forms.Form):
    """支払通知書を作成する担当者を選択するフォーム。"""

    created_by = forms.ModelChoiceField(
        label="作成担当者",
        queryset=Operator.objects.none(),
        empty_label="作成担当者を選択してください",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["created_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role__in=[
                    Operator.Role.MANAGER,
                    Operator.Role.CREATOR,
                ],
            ).order_by("id")
        )

class PaymentConfirmationForm(forms.Form):
    """支払通知書の確認結果を登録するフォーム。"""

    checked_by = forms.ModelChoiceField(
        label="確認担当者",
        queryset=Operator.objects.none(),
        empty_label="確認担当者を選択してください",
    )

    result = forms.ChoiceField(
        label="確認結果",
        choices=[
            (
                PaymentRecord.Status.CONFIRMED,
                "確認済み",
            ),
            (
                PaymentRecord.Status.CORRECTION_REQUIRED,
                "要修正",
            ),
        ],
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        label="確認内容・修正理由",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "要修正の場合は、修正箇所や理由を"
                    "入力してください。"
                ),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["checked_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role__in=[
                    Operator.Role.MANAGER,
                    Operator.Role.CHECKER,
                ],
            ).order_by("id")
        )

    def clean(self):
        cleaned_data = super().clean()

        result = cleaned_data.get("result")
        comment = (
            cleaned_data.get("comment")
            or ""
        ).strip()

        if (
            result
            == PaymentRecord.Status.CORRECTION_REQUIRED
            and not comment
        ):
            self.add_error(
                "comment",
                "要修正の場合は修正理由を入力してください。",
            )

        return cleaned_data
    
class ProcessingErrorUpdateForm(forms.Form):
    """処理エラーの対応状況を更新するフォーム。"""

    resolved_by = forms.ModelChoiceField(
        label="対応担当者",
        queryset=Operator.objects.none(),
        empty_label="対応担当者を選択してください",
    )

    resolution_status = forms.ChoiceField(
        label="対応状況",
        choices=ProcessingError.ResolutionStatus.choices,
    )

    resolution_note = forms.CharField(
        label="対応内容",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": (
                    "確認した内容や修正方法を"
                    "入力してください。"
                ),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["resolved_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
            ).order_by(
                "role",
                "id",
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        resolution_status = cleaned_data.get(
            "resolution_status"
        )
        resolution_note = (
            cleaned_data.get("resolution_note")
            or ""
        ).strip()

        if (
            resolution_status
            == ProcessingError
            .ResolutionStatus
            .RESOLVED
            and not resolution_note
        ):
            self.add_error(
                "resolution_note",
                (
                    "解消済みにする場合は、"
                    "対応内容を入力してください。"
                ),
            )

        return cleaned_data


class PaymentRecordEditForm(forms.ModelForm):
    """要修正となった支払対象データを編集するフォーム。"""

    edited_by = forms.ModelChoiceField(
        label="修正担当者",
        queryset=Operator.objects.none(),
        empty_label="修正担当者を選択してください",
    )

    payment_date = forms.DateField(
        label="支払日",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
            },
        ),
    )

    class Meta:
        model = PaymentRecord
        fields = [
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
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3},
            ),
            "description": forms.Textarea(
                attrs={"rows": 4},
            ),
            "notes": forms.Textarea(
                attrs={"rows": 3},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["edited_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role__in=[
                    Operator.Role.MANAGER,
                    Operator.Role.CREATOR,
                ],
            ).order_by("id")
        )

    def clean_issue_number(self):
        """別データと発行番号が重複していないか確認する。"""

        issue_number = (
            self.cleaned_data["issue_number"]
            .strip()
        )

        duplicate_exists = (
            PaymentRecord.objects
            .filter(issue_number=issue_number)
            .exclude(pk=self.instance.pk)
            .exists()
        )

        if duplicate_exists:
            raise forms.ValidationError(
                "同じ発行番号がすでに登録されています。"
            )

        return issue_number

    def clean_registration_number(self):
        """事業者登録番号の形式を確認する。"""

        registration_number = (
            self.cleaned_data.get(
                "registration_number",
                "",
            )
            or ""
        ).strip()

        if (
            registration_number
            and not re.fullmatch(
                r"T\d{13}",
                registration_number,
            )
        ):
            raise forms.ValidationError(
                "事業者登録番号は、"
                "Tと13桁の数字で入力してください。"
            )

        return registration_number

    def clean_payment_amount(self):
        """支払金額が0以上であることを確認する。"""

        payment_amount = self.cleaned_data[
            "payment_amount"
        ]

        if payment_amount < 0:
            raise forms.ValidationError(
                "支払金額には0以上の値を入力してください。"
            )

        return payment_amount


class PaymentCompletionForm(forms.Form):
    """確認済みの支払対象を完了にするフォーム。"""

    completed_by = forms.ModelChoiceField(
        label="完了処理担当者",
        queryset=Operator.objects.none(),
        empty_label="管理者/SVを選択してください",
    )

    comment = forms.CharField(
        label="完了コメント",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "必要に応じて引き渡し内容などを"
                    "入力してください。"
                ),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["completed_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role=Operator.Role.MANAGER,
            ).order_by("id")
        )


class DuplicateReviewForm(forms.Form):
    """重複候補について、人による確認結果を登録するフォーム。"""

    reviewed_by = forms.ModelChoiceField(
        label="重複確認担当者",
        queryset=Operator.objects.none(),
        empty_label="確認担当者を選択してください",
    )

    result = forms.ChoiceField(
        label="重複確認結果",
        choices=[
            (
                PaymentRecord
                .DuplicateCheckResult
                .ALLOWED,
                "正当な別支払",
            ),
            (
                PaymentRecord
                .DuplicateCheckResult
                .DUPLICATE,
                "重複確定",
            ),
        ],
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        label="判断理由",
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "別キャンペーンのため正当な別支払、"
                    "既存データと同一のため重複、など"
                ),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["reviewed_by"].queryset = (
            Operator.objects.filter(
                is_active=True,
                role__in=[
                    Operator.Role.MANAGER,
                    Operator.Role.CREATOR,
                ],
            ).order_by("id")
        )