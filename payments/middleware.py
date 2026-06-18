from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


class ReadOnlyDemoMiddleware:
    """公開デモ環境で一般画面の更新操作を停止する。"""

    unsafe_methods = {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_read_only = getattr(
            settings,
            "READ_ONLY_DEMO",
            False,
        )

        is_update_request = (
            request.method in self.unsafe_methods
        )

        is_admin_request = request.path.startswith(
            "/admin/"
        )

        if (
            is_read_only
            and is_update_request
            and not is_admin_request
        ):
            messages.warning(
                request,
                (
                    "このサイトは閲覧専用デモです。"
                    "データの登録・変更操作はできません。"
                ),
            )

            referer = request.META.get(
                "HTTP_REFERER"
            )

            if (
                referer
                and url_has_allowed_host_and_scheme(
                    referer,
                    allowed_hosts={
                        request.get_host()
                    },
                    require_https=request.is_secure(),
                )
            ):
                return redirect(referer)

            return redirect(
                "payments:home"
            )

        return self.get_response(request)