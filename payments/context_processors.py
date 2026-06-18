from django.conf import settings


def demo_settings(request):
    """公開デモに関する設定をテンプレートへ渡す。"""

    return {
        "read_only_demo": getattr(
            settings,
            "READ_ONLY_DEMO",
            False,
        ),
    }