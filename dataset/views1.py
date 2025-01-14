from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import Dataset, User, Comment, Request, AnnotationRequest, AnnotationResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.core.files.storage import default_storage

import pandas as pd
from fastparquet import ParquetFile
import pygwalker as pyg
import os
from django.conf import settings
from djangoaddicts.pygwalker.views import PygWalkerView
from django.utils.html import format_html
from djangoaddicts.pygwalker.views import StaticCsvPygWalkerView
from djangoaddicts.pygwalker.views import PygWalkerView
import json
import datetime


def dataset_list_fa(request):
    q = request.GET.get('q')
    if q is not None:
        all_datasets = Dataset.objects.filter(owner__icontains=q).order_by('-id')
    else:
        all_datasets = Dataset.objects.all().order_by('-id')
    page_number = request.GET.get('page')
    paginator = Paginator(all_datasets, 9)
    datasets = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_list_fa.html', context={'datasets': datasets})


def dataset_detail_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)

    if request.method == "POST" and 'submit_dataset_comment' in request.POST:
        text = request.POST.get('text')
        Comment.objects.create(text=text, dataset=dataset, user=request.user)

    if request.method == "POST" and 'submit_dataset_request' in request.POST:
        Request.objects.create(dataset=dataset, user=request.user)

    ##########
    ## get parq
    # print(os.path.join(settings.MEDIA_ROOT + '/datasets_parq/', 'bike.parq'))
    # pf = ParquetFile(os.path.join(settings.MEDIA_ROOT + '/datasets_parq/', 'bike.parq'))
    # df = pf.to_pandas()
    # df2 = pf.to_pandas(['col1', 'col2'], categories=['col1'])
    # print(df)

    ##########
    return render(request, 'dataset/dataset_detail_fa.html', context={'dataset': dataset})


def get_absolute_url(self, dataset):
    return reverse()


def dataset_viewer_fa(request):
    # https://blog.jcharistech.com/2023/10/15/how-to-use-pygwalker-with-flask-in-python/

    # pf = ParquetFile(os.path.join(settings.MEDIA_ROOT + '/datasets_parq/', 'bike.parq'))
    # df = pf.to_pandas()

    df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
    # html_obj = pyg.walk(df[:10], spec="./chart_meta_0.json", return_html=True)
    html_obj = pyg.walk(df[:2], return_html=True)
    print('*******************************************************')
    print(df[:2])
    print('*******************************************************')
    print(format_html("<h1>Hello</h1>"))
    return render(request, 'dataset/dataset_viewer_fa.html', context={'html_obj': html_obj})



def dataset_viewer_fa1(request):
    html_obj = MyPygWalkerView()
    return render(request, 'dataset/dataset_viewer_fa.html', context={'html_obj': html_obj})


def dataset_col(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    return render(request, 'dataset/dataset_col.html', context={'dataset': dataset})


def dataset_import(request):
    return render(request, 'dataset/dataset_import.html', context={})


def dataset_define(request):
    return render(request, 'dataset/dataset_define.html', context={})


def dataset_step(request):
    return render(request, 'dataset/dataset_step.html', context={})


def dataset_define_stepper_fa(request):
    return render(request, 'dataset/dataset_define_stepper_fa.html', context={})

def dataset_load_stepper_fa(request):
    return render(request, 'dataset/dataset_load_stepper_fa.html', context={})


def saveTempMetaData(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        if request.method == 'POST':
            data = json.load(request)
            dataset = data.get('dataset')
            print(dataset['dataset_name'])

            dataset_name = dataset['dataset_name']
            dataset_owner = dataset['dataset_owner']
            dataset_language = dataset['dataset_language']
            dataset_license = dataset['dataset_license']
            dataset_format = dataset['dataset_format']
            dataset_desc = dataset['dataset_desc']
            dataset_columnDataType = dataset['dataset_columnDataType']

            Dataset.objects.create(user=request.user
                                   , name=dataset_name
                                   , owner=dataset_owner
                                   , language=dataset_language
                                   , license=dataset_license
                                   , format=dataset_format
                                   , desc=dataset_desc
                                   , columnDataType=dataset_columnDataType
                                   , datasetDate=datetime.datetime.now()
                                   )
        return render(request, 'dataset/dataset_define_stepper_fa.html', context={})


def dataset_ner(request):
    return render(request, 'dataset/dataset_ner.html', context={})


class MyPygWalkerView(StaticCsvPygWalkerView):
    csv_file = os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv')
    template_name = "dataset/dataset_viewer_fa.html"


class MyPygWalkerView1(PygWalkerView):
    queryset = Dataset.objects.all()
    template_name = "dataset/dataset_viewer_fa.html"


class MyPygWalkerView2(PygWalkerView):
    df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
    queryset = df[:10]
    template_name = "dataset/dataset_viewer_fa.html"


def dataset_annotation_request_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    annotation_requests = AnnotationRequest.objects.filter(dataset=dataset.id).order_by('-requestDateTime')
    return render(request, 'dataset/dataset_annotation_request_fa.html', context={'dataset': dataset,'annotation_requests': annotation_requests})

def create_annotation_request(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        if request.method == 'POST':
            data = json.load(request)
            annotationReq = data.get('annotationReq')
            print(annotationReq['annotationReq_desc'])

            annotationReq_dataset_id = annotationReq['annotationReq_dataset_id']
            annotationReq_startRecord = annotationReq['annotationReq_startRecord']
            annotationReq_endRecord = annotationReq['annotationReq_endRecord']
            annotationReq_priceType = annotationReq['annotationReq_priceType']
            annotationReq_estimatedPrice = annotationReq['annotationReq_estimatedPrice']
            annotationReq_desc = annotationReq['annotationReq_desc']
            annotationReq_labelOptions = annotationReq['annotationReq_labelOptions']

            #dataset = Dataset.objects.filter(id=annotationReq_dataset_id).get()
            AnnotationRequest.objects.create(dataset=request.dataset.id
                                   , startRecord=annotationReq_startRecord
                                   , endRecord=annotationReq_endRecord
                                   , priceType=annotationReq_priceType
                                   , estimatedPrice=annotationReq_estimatedPrice
                                   , desc=annotationReq_desc
                                   , labelOptions=annotationReq_labelOptions
                                   , requestDateTime=datetime.datetime.now()
                                   )

            return render(request, 'dataset/dataset_annotation_request_fa.html', context={})



def dataset_annotation_list_fa(request):
    page_number = 1

    if request.method == 'GET':
        q = request.GET.get('q')
        if q is not None:
            all_annotation_requests = AnnotationRequest.objects.filter(owner__icontains=q).order_by('-id')

    elif request.method == 'POST':
        all_annotation_requests = AnnotationRequest.objects.all().order_by('-id')
        AnnotationResponse.objects.create(dataset=request.dataset.id
                                         , startRecord=annotationReq_startRecord
                                         , endRecord=annotationReq_endRecord
                                         , priceType=annotationReq_priceType
                                         , estimatedPrice=annotationReq_estimatedPrice
                                         , desc=annotationReq_desc
                                         , labelOptions=annotationReq_labelOptions
                                         , requestDateTime=datetime.datetime.now()
                                         )
    page_number = request.GET.get('page')
    paginator = Paginator(all_annotation_requests, 9)
    annotation_requests = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_annotation_list_fa.html', context={'annotation_requests': annotation_requests})




