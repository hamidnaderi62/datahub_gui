from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import Dataset, User, Comment, PredefinedTag, Request, AnnotationRequest, AnnotationResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.core.files.storage import default_storage
from django.contrib.auth.decorators import login_required

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
from taggit.models import Tag
from django.db.models import Count


def dataset_list_fa(request):
    q = request.GET.get('q')
    if q is not None:
        all_datasets = Dataset.objects.filter(dataset_tags__icontains=q).order_by('-id')
    else:
        all_datasets = Dataset.objects.all().order_by('-id')
    page_number = request.GET.get('page')
    paginator = Paginator(all_datasets, 9)
    datasets = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_list_fa.html', context={'datasets': datasets})


def dataset_detail_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    tags = dataset.tags.all()
    similar_datasets = Dataset.objects.filter(tags__in=tags).exclude(id=dataset.id).distinct()
    similar_datasets = similar_datasets.annotate(num_common_tags=Count('tags')).order_by('-num_common_tags')[:3]
    print(similar_datasets)

    if request.method == "POST" and 'submit_dataset_comment' in request.POST:
        text = request.POST.get('text')
        Comment.objects.create(text=text, dataset=dataset, user=request.user)

    elif request.method == "POST" and 'submit_dataset_request' in request.POST:
        Request.objects.create(dataset=dataset, user=request.user)

    # show dataset viewer
    elif request.method == "POST" and 'submit_dataset_viewer' in request.POST:
        df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
        html_obj = pyg.walk(df[:10], return_html=True)
        print(df[:2])
        return render(request, 'dataset/dataset_detail_fa.html', context={'dataset': dataset,'similar_datasets': similar_datasets, 'html_obj': html_obj})

    return render(request, 'dataset/dataset_detail_fa.html', context={'dataset': dataset, 'similar_datasets': similar_datasets})


def get_absolute_url(self, dataset):
    return reverse()


@login_required
def dataset_like_fa(request, pk):
    dataset = get_object_or_404(Dataset, id=pk)
    if request.user in dataset.likes.all():
        dataset.likes.remove(request.user)
        liked = False
    else:
        dataset.likes.add(request.user)
        liked = True
    return JsonResponse({'liked': liked, 'total_likes': dataset.likes.count()})


def dataset_viewer_fa(request):
    # https://blog.jcharistech.com/2023/10/15/how-to-use-pygwalker-with-flask-in-python/

    # pf = ParquetFile(os.path.join(settings.MEDIA_ROOT + '/datasets_parq/', 'bike.parq'))
    # df = pf.to_pandas()

    df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
    # html_obj = pyg.walk(df[:10], spec="./chart_meta_0.json", return_html=True)
    # data = {'Category': ['A','B','C'], 'Value':[10,20,30]}
    # df = pd.DataFrame(data=data)
    pygwalker_html = pyg.walk(df[:10], return_html=True)
    print('*******************************************************')
    print(df[:2])
    print('*******************************************************')
    print(type(pygwalker_html))
    #return HttpResponse(pygwalker_html)
    return render(request, 'dataset/dataset_viewer_fa.html', context={'pygwalker_html': pygwalker_html})



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
    dataset_tags = PredefinedTag.objects.values_list('tag', flat=True)
    dataset_tags_list = list(dataset_tags)
    print(dataset_tags_list)
    return render(request, 'dataset/dataset_define_stepper_fa.html', context={'dataset_tags_list': dataset_tags_list })

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
            dataset_tags = dataset['dataset_tags']
            dataset_columnDataType = dataset['dataset_columnDataType']

            new_dataset = Dataset.objects.create(user=request.user
                                   , name=dataset_name
                                   , owner=dataset_owner
                                   , language=dataset_language
                                   , license=dataset_license
                                   , format=dataset_format
                                   , desc=dataset_desc
                                   , dataset_tags=dataset_tags
                                   #, tags=dataset_tags
                                   , columnDataType=dataset_columnDataType
                                   , datasetDate=datetime.datetime.now()
                                   )
            # input_tags = ",".join(f"'{item.strip()}'" for item in dataset_tags.split(","))
            input_tags = dataset_tags.split(",")
            print(input_tags)
            new_dataset.tags.set(input_tags)
        return render(request, 'dataset/dataset_define_stepper_fa.html', context={})


def dataset_ner(request):
    return render(request, 'dataset/dataset_ner.html', context={})




def dataset_annotation_request_fa(request, pk=None):
    if request.method == 'POST':
        if 'btn_annotation_request_cancel' in request.POST:
            AnnotationRequest.objects.filter(id=request.POST.get('annotation_request_id')).update(annotationStatus='Canceled', responseDateTime=datetime.datetime.now())

        if 'btn_annotation_response_accept' in request.POST:
            acceptedAnnotationResponse = AnnotationResponse.objects.filter(id=request.POST.get('annotation_response_id')).get()
            annotationRequest = AnnotationRequest.objects.filter(id=acceptedAnnotationResponse.annotationRequest.id).get()
            totalFinalPrice = annotationRequest.totalRecords * acceptedAnnotationResponse.suggestedPrice

            AnnotationResponse.objects.filter(annotationRequest=acceptedAnnotationResponse.annotationRequest).update(responseType='Reject', responseDate=datetime.datetime.now())
            AnnotationResponse.objects.filter(id=acceptedAnnotationResponse.id).update(responseType='Accept',responseDate=datetime.datetime.now())
            AnnotationRequest.objects.filter(id=acceptedAnnotationResponse.annotationRequest.id).update( annotationStatus='Accepted', finalPrice=acceptedAnnotationResponse.suggestedPrice, totalFinalPrice=totalFinalPrice, responseDateTime=datetime.datetime.now())

    dataset = get_object_or_404(Dataset, id=pk)
    annotation_requests = AnnotationRequest.objects.filter(dataset=dataset.id).order_by('-requestDateTime')
    annotation_responses = AnnotationResponse.objects.filter(dataset=dataset.id).order_by('-responseDate')
    return render(request, 'dataset/dataset_annotation_request_fa.html', context={'dataset': dataset,'annotation_requests': annotation_requests,'annotation_responses': annotation_responses})

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
            annotationReq_totalRecords = float(annotationReq_endRecord) - float(annotationReq_startRecord) + 1

            dataset = Dataset.objects.filter(id=annotationReq_dataset_id).get()
            AnnotationRequest.objects.create(dataset=dataset
                                   , startRecord=annotationReq_startRecord
                                   , endRecord=annotationReq_endRecord
                                   , totalRecords=annotationReq_totalRecords
                                   , priceType=annotationReq_priceType
                                   , estimatedPrice=annotationReq_estimatedPrice
                                   , tags=dataset.dataset_tags
                                   , desc=annotationReq_desc
                                   , labelOptions=annotationReq_labelOptions
                                   , requestDateTime=datetime.datetime.now()
                                   )

            return render(request, 'dataset/dataset_annotation_request_fa.html', context={})


def dataset_annotation_list_fa(request):
    all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').select_related('dataset').order_by('-id')
    if request.method == "GET":
        q = request.GET.get('q')
        print(q)
        if q:
            all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested', tags__icontains=q).select_related('dataset').order_by('-requestDateTime')
    elif request.method == "POST" and 'btn_annotation_request_accept' in request.POST:
        dataset_id = request.POST.get('dataset_id')
        annotationRequest_id = request.POST.get('annotation_request_id')
        annotationRes_suggestedPrice = request.POST.get('annotationRes_suggestedPrice')
        annotationRes_text = request.POST.get('annotationRes_text')

        annotationRequest = AnnotationRequest.objects.filter(id=annotationRequest_id).get()
        dataset = Dataset.objects.filter(id=dataset_id).get()

        AnnotationResponse.objects.create(dataset=dataset
                                          , annotationRequest=annotationRequest
                                          , user=request.user
                                          , suggestedPrice=annotationRes_suggestedPrice
                                          , text=annotationRes_text
                                          , responseDate=datetime.datetime.now()
                                          )

        all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').order_by('-requestDateTime').select_related('dataset')
    page_number = request.GET.get('page')
    paginator = Paginator(all_annotation_requests, 9)
    annotation_requests = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_annotation_list_fa.html', context={'annotation_requests': annotation_requests})


def dataset_annotation_record_fa(request, pk=None):
    return render(request, 'dataset/dataset_annotation_record_fa.html', context={})


class MyPygWalkerView1(StaticCsvPygWalkerView):
    csv_file = os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv')
    template_name = "dataset/dataset_viewer_fa.html"


class MyPygWalkerView(PygWalkerView):
    queryset = Dataset.objects.all()
    template_name = "dataset/dataset_viewer_fa.html"


class MyPygWalkerView2(PygWalkerView):
    df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
    queryset = df[:10]
    template_name = "dataset/dataset_viewer_fa.html"