
from django.urls import path
from . import views

from dataset.views import MyPygWalkerView

app_name = "dataset"

urlpatterns = [
    path('dataset_list_fa', views.dataset_list_fa, name="dataset_list_fa"),
    path('dataset_detail_fa/<int:pk>', views.dataset_detail_fa, name="dataset_detail_fa"),
    path('dataset_like_fa/<int:pk>', views.dataset_like_fa, name="dataset_like_fa"),

    path('dataset_download_fa/<int:pk>', views.dataset_download_fa, name="dataset_download_fa"),

    path('predefined_tags/', views.predefined_tags, name="predefined_tags"),
    path('dataset_new_stepper_fa', views.dataset_new_stepper_fa, name="dataset_new_stepper_fa"),
    path('dataset_define_stepper_fa', views.dataset_define_stepper_fa, name="dataset_define_stepper_fa"),
    path('saveTempMetaData', views.saveTempMetaData, name="saveTempMetaData"),
    path('upload_dataset', views.upload_dataset, name="upload_dataset"),

    path('dataset_load_stepper_fa', views.dataset_load_stepper_fa, name="dataset_load_stepper_fa"),

    # path('dataset_viewer_fa', views.dataset_viewer_fa, name="dataset_viewer_fa"),

    path("dataset_viewer_fa", MyPygWalkerView.as_view(), name="dataset_viewer_fa"),

    path('dataset_col/<int:pk>', views.dataset_col, name="dataset_col"),

    path('dataset_import', views.dataset_import, name="dataset_import"),

    path('dataset_define', views.dataset_define, name="dataset_define"),

    path('dataset_step', views.dataset_step, name="dataset_step"),

    path('dataset_ner', views.dataset_ner, name="dataset_ner"),



    path('dataset_annotation_request_fa/<int:pk>', views.dataset_annotation_request_fa, name="dataset_annotation_request_fa"),

    path('create_annotation_request', views.create_annotation_request, name="create_annotation_request"),

    path('dataset_annotation_list_fa', views.dataset_annotation_list_fa, name="dataset_annotation_list_fa"),

    path('dataset_annotation_record_fa/<int:pk>', views.dataset_annotation_record_fa, name="dataset_annotation_record_fa"),

    path('download_file_from_cloud', views.download_file_from_cloud, name='download_file_from_cloud'),


]

