from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.home, name="home"),
    path(
        "payments/",
        views.payment_record_list,
        name="payment_record_list",
    ),
    path(
        "payments/import/",
        views.import_payment_records,
        name="import_payment_records",
    ),
    path(
        "errors/",
        views.processing_error_list,
        name="processing_error_list",
    ),
    path(
        "errors/<int:pk>/",
        views.processing_error_detail,
        name="processing_error_detail",
    ),
    path(
        "errors/<int:pk>/update/",
        views.update_processing_error,
        name="update_processing_error",
    ),
    path(
        "payments/<int:pk>/",
        views.payment_record_detail,
        name="payment_record_detail",
    ),
    path(
        "payments/<int:pk>/duplicate-review/",
        views.review_duplicate_candidate,
        name="review_duplicate_candidate",
    ),
    path(
        "payments/<int:pk>/edit/",
        views.edit_payment_record,
        name="edit_payment_record",
    ),
    path(
        "payments/<int:pk>/generate/",
        views.generate_payment_document,
        name="generate_payment_document",
    ),
    path(
        "documents/<int:pk>/download/",
        views.download_generated_document,
        name="download_generated_document",
    ),
    path(
        "payments/<int:pk>/confirm/",
        views.confirm_payment_record,
        name="confirm_payment_record",
    ),
    path(
        "payments/<int:pk>/complete/",
        views.complete_payment_record,
        name="complete_payment_record",
    ),
]