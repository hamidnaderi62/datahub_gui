
from django.urls import path
from . import views
from .external_import_views import receive_external_import

from dataset.views import MyPygWalkerView

app_name = "dataset"

urlpatterns = [
    path('api/v1/external-imports', receive_external_import, name='receive_external_import'),
    path('dataset_list', views.dataset_list_fa, name="dataset_list"),
    path('dataset_detail/<int:pk>', views.dataset_detail_fa, name="dataset_detail"),
    path('dataset_like/<int:pk>', views.dataset_like_fa, name="dataset_like"),
    path('dataset_download/<int:pk>', views.dataset_download_fa, name="dataset_download"),
    path('publish_dataset_version/<int:version_id>', views.publish_dataset_version_fa, name="publish_dataset_version"),
    path('pipeline_status/<int:version_id>', views.pipeline_status, name="pipeline_status"),

    # Legacy aliases kept for old bookmarks and integrations.
    path('dataset_list_fa', views.dataset_list_fa, name="dataset_list_fa"),
    path('dataset_detail_fa/<int:pk>', views.dataset_detail_fa, name="dataset_detail_fa"),
    path('dataset_like_fa/<int:pk>', views.dataset_like_fa, name="dataset_like_fa"),
    path('dataset_download_fa/<int:pk>', views.dataset_download_fa, name="dataset_download_fa"),
    path('publish_dataset_version_fa/<int:version_id>', views.publish_dataset_version_fa, name="publish_dataset_version_fa"),

    path('predefined_tags/', views.predefined_tags, name="predefined_tags"),
    path('dataset_new_stepper', views.dataset_new_stepper_fa, name="dataset_new_stepper"),
    path('dataset_define_stepper', views.dataset_define_stepper_fa, name="dataset_define_stepper"),
    path('saveTempMetaData', views.saveTempMetaData, name="saveTempMetaData"),
    path('upload_batches', views.create_upload_batch, name="create_upload_batch"),
    path('upload_batches/update', views.update_upload_batch, name="update_upload_batch"),
    path('upload_direct/create', views.create_direct_upload, name="create_direct_upload"),
    path('upload_direct/part-url', views.direct_upload_part_url, name="direct_upload_part_url"),
    path('upload_direct/complete', views.complete_direct_upload, name="complete_direct_upload"),
    path('upload_direct/abort', views.abort_direct_upload, name="abort_direct_upload"),
    path('upload_dataset', views.upload_dataset, name="upload_dataset"),

    path('dataset_load_stepper', views.dataset_load_stepper_fa, name="dataset_load_stepper"),

    path("dataset_viewer", MyPygWalkerView.as_view(), name="dataset_viewer"),

    path('dataset_files/<int:pk>/', views.dataset_files_fa, name='dataset_files'),

    path('download_file_from_cloud', views.download_file_from_cloud, name='download_file_from_cloud'),



    path('dataset_ner', views.dataset_ner, name="dataset_ner"),

    path('dataset_annotation_request/<int:pk>', views.dataset_annotation_request_fa, name="dataset_annotation_request"),

    path('create_annotation_request', views.create_annotation_request, name="create_annotation_request"),

    path('dataset_annotation_list', views.dataset_annotation_list_fa, name="dataset_annotation_list"),

    path('dataset_annotation_record/<int:pk>', views.dataset_annotation_record_fa, name="dataset_annotation_record"),

    # Legacy dataset workflow URLs.
    path('dataset_new_stepper_fa', views.dataset_new_stepper_fa, name="dataset_new_stepper_fa"),
    path('dataset_define_stepper_fa', views.dataset_define_stepper_fa, name="dataset_define_stepper_fa"),
    path('dataset_load_stepper_fa', views.dataset_load_stepper_fa, name="dataset_load_stepper_fa"),
    path("dataset_viewer_fa", MyPygWalkerView.as_view(), name="dataset_viewer_fa"),
    path('dataset_files_fa/<int:pk>/', views.dataset_files_fa, name='dataset_files_fa'),
    path('dataset_annotation_request_fa/<int:pk>', views.dataset_annotation_request_fa, name="dataset_annotation_request_fa"),
    path('dataset_annotation_list_fa', views.dataset_annotation_list_fa, name="dataset_annotation_list_fa"),
    path('dataset_annotation_record_fa/<int:pk>', views.dataset_annotation_record_fa, name="dataset_annotation_record_fa"),




]
