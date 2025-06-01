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
from datetime import datetime
from taggit.models import Tag
from django.db.models import Count
import math
from django.views.generic import TemplateView
from django.utils.safestring import mark_safe




# Get
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
        label, score = analyze_sentiment(text)
        Comment.objects.create(text=text, dataset=dataset, user=request.user, sentiment_label=label, sentiment_score=score)

    elif request.method == "POST" and 'submit_dataset_request' in request.POST:
        Request.objects.create(dataset=dataset, user=request.user)

    # show dataset viewer
    elif request.method == "POST" and 'submit_dataset_viewer' in request.POST:
        df = pd.read_csv(os.path.join(settings.MEDIA_ROOT + '/datasets_csv/', 'bike.csv'))
        html_obj = pyg.walk(df[:10], return_html=True)
        print(df[:2])
        return render(request, 'dataset/dataset_detail_fa.html', context={'dataset': dataset,'similar_datasets': similar_datasets, 'html_obj': html_obj})

    return render(request, 'dataset/dataset_detail_fa.html', context={'dataset': dataset, 'similar_datasets': similar_datasets})


def dataset_download_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    # download_links = dataset.downloadLink
    return render(request, 'dataset/dataset_download_fa.html', context={'dataset': dataset})


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



def dataset_viewer_fa1(request):
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
    # print(type(pygwalker_html))
    #return HttpResponse(pygwalker_html)
    return render(request, 'dataset/dataset_viewer_fa.html', context={'pygwalker_html': mark_safe(pygwalker_html)})



def dataset_col(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    return render(request, 'dataset/dataset_col.html', context={'dataset': dataset})


def dataset_import(request):
    return render(request, 'dataset/dataset_import.html', context={})


def dataset_define(request):
    return render(request, 'dataset/dataset_define.html', context={})


def dataset_step(request):
    return render(request, 'dataset/dataset_step.html', context={})


def predefined_tags(request):
    dataset_tags = list(PredefinedTag.objects.values_list('tag', flat=True))
    return JsonResponse(dataset_tags, safe=False)


def dataset_new_stepper_fa(request):
    return render(request, 'dataset/dataset_new_stepper_fa.html', context={})


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
                                   , datasetDate=datetime.now()
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


# read & show sample data from local file
class MyPygWalkerView1(TemplateView):
    template_name = "dataset/dataset_viewer_fa.html"

    def get_pygwalker_config1(self):
        """Returns a config to show ONLY the data tab"""
        return {
            "config": {
                "menu": {
                    "data": True,  # Show Data Tab
                    "visualize": False,  # Hide Visualize Tab
                    "export": False,  # Hide Export Button
                },
                "theme": "light",  # Light theme
                "show_cloud_tool": False  # Hide Cloud options
            }
        }

    def get_dataframe(self, dataset_id):

        '''
        # Allow only CSV files
        if not safe_filename.lower().endswith('.csv'):
            logger.error(f"Invalid file type: {safe_filename}")
            return pd.DataFrame()


        # Check file size before reading (e.g., 50MB limit)
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        if os.path.getsize(csv_path) > MAX_FILE_SIZE:
            logger.error(f"File too large: {safe_filename}")
            return pd.DataFrame()
        '''


        csv_path = os.path.join(settings.MEDIA_ROOT, 'datasets_csv', 'bike.csv')
        try:
            # Read the entire file first to get row count
            df = pd.read_csv(csv_path)

            # Calculate 10% of the data (rounded up)
            sample_size = math.ceil(len(df) * 0.1)

            # Return random sample of 10%
            return df.sample(n=sample_size, random_state=42)  # random_state for reproducibility

        except Exception as e:
            print(f"Error loading CSV: {str(e)}")
            return pd.DataFrame()  # Return empty dataframe as fallback
        # return pd.read_csv(csv_path).head(20)

    def get_context_data(self):
        context = super().get_context_data()
        dataset_id = self.request.GET.get('dataset_id')
        dataset_info = Dataset.objects.filter(id=dataset_id).get()
        df = self.get_dataframe(dataset_id)
        if df.empty:
            context['error'] = "Could not load dataset"
        else:
            context['pygwalker_html'] = mark_safe(pyg.walk(df).to_html())
            # context['pygwalker_html'] = mark_safe(pyg.walk(df, spec=json.dumps(self.get_pygwalker_config()), return_html=True).to_html())
            context['dataset'] = dataset_info
        return context

# Read  & show sample data from first dataset url file (csv,parquet)
import tempfile
class MyPygWalkerView(TemplateView):
    template_name = "dataset/dataset_viewer_fa.html"
    AUTH_TOKEN = '391af3cea0e0248b92ad2d2671d4eaa8669854be'

    def get_first_download_url(self, download_links):
        """Extract first download URL from dataset's downloadLink"""
        try:
            if download_links and isinstance(download_links, list):
                return download_links[0]['url']
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing downloadLink: {str(e)}")
        return None

    def get_file_from_url(self, file_url):
        """Download file from URL and return temporary file path"""
        if not file_url:
            return None

        try:
            response = requests.get(
                file_url,
                headers={'X-Auth-Token': self.AUTH_TOKEN},
                stream=True
            )
            response.raise_for_status()

            # Determine file type from extension
            filename = file_url.split('/')[-1]
            file_ext = filename.split('.')[-1].lower()

            # Create a temporary file to store the downloaded data
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name

        except Exception as e:
            print(f"Error downloading file: {str(e)}")
            return None

    def get_pygwalker_config1(self):
        """Returns a config to show ONLY the data tab"""
        return {
            "config": {
                "menu": {
                    "data": True,  # Show Data Tab
                    "visualize": False,  # Hide Visualize Tab
                    "export": False,  # Hide Export Button
                },
                "theme": "light",  # Light theme
                "show_cloud_tool": False  # Hide Cloud options
            }
        }

    def get_pygwalker_config(self):
        """Returns a config to show ONLY the data tab"""
        return {
            "config": {
                "menu": {
                    "data": True,
                    "visualize": False,
                    "export": False,
                    "help": False
                },
                "header": {
                    "title": "Data Viewer",
                    "show": True
                },
                "themeKey": "vega",
                "themeConfig": {
                    "currentTheme": "light",
                    "themeSet": "light"
                },
                "showCloudTool": False,
                "enableExportData": False,
                "enableExportImage": False
            }
        }




    def read_data_file(self, file_path):
        """Read data file (CSV or Parquet) into DataFrame"""
        file_ext = file_path.split('.')[-1].lower()
        try:
            if file_ext == 'parquet':
                return pd.read_parquet(file_path)
            else:  # default to CSV
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading file: {str(e)}")
            return pd.DataFrame()

    def sample_dataframe(self, df):
        """Take 10% sample of dataframe (max 100 rows)"""
        if df.empty:
            return df

        sample_size = min(100, max(1, math.ceil(len(df) * 0.1)))
        return df.sample(n=sample_size, random_state=42)  # random_state for reproducibility

    def get_context_data(self):
        context = super().get_context_data()
        dataset_id = self.request.GET.get('dataset_id')

        if not dataset_id:
            context['error'] = "No dataset ID provided"
            return context

        try:
            dataset = Dataset.objects.get(id=dataset_id)
            context['dataset'] = dataset

            # Get download links (assuming it's already a Python list)
            download_links = dataset.downloadLink

            # Get first download URL from downloadLink
            file_url = self.get_first_download_url(download_links)

            if not file_url:
                context['error'] = "No valid download URL found"
                return context

            # Download and process the file
            tmp_file_path = self.get_file_from_url(file_url)
            if not tmp_file_path:
                context['error'] = "Could not download file"
                return context
            df = self.read_data_file(tmp_file_path)

            # Clean up temporary file
            try:
                os.unlink(tmp_file_path)
            except:
                pass

            if df.empty:
                context['error'] = "Could not load dataset"
            else:
                sampled_df = self.sample_dataframe(df)
                pyg_html = pyg.walk(
                    sampled_df
                    , spec=self.get_pygwalker_config()
                    , return_html=True
                ).to_html()
                context['pygwalker_html'] = mark_safe(pyg_html)

        except Dataset.DoesNotExist:
            context['error'] = "Dataset not found"

        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            context['error'] = "An unexpected error occurred"

        return context


###################################################
# save metadata of dataset to DB and upload file to cloud storage
###################################################
import os
import json
import re
import requests
import hashlib
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Dataset  # Make sure to import your Dataset model


# Cloud storage configuration
ACCOUNT = 'AUTH_aiahr-ae5aa48e'
AUTH_TOKEN = '391af3cea0e0248b92ad2d2671d4eaa8669854be'
STORAGE_BASE_URL = f'https://storage.aiahura.com/v1/{ACCOUNT}/'

# CONTAINER_NAME = 'cn1'
# CLOUD_STORAGE_URL = f'https://storage.aiahura.com/v1/{ACCOUNT}/{CONTAINER_NAME}/'

# Temporary storage for upload tracking (in production, use database or Redis)
upload_tracker = {}


def validate_upload_id(upload_id):
    """Validate the upload ID format (timestamp-filename)"""
    if not upload_id:
        return False
    parts = upload_id.split('-', 1)
    if len(parts) != 2:
        return False
    timestamp, filename = parts
    return re.match(r'^\d+\.\d+$', timestamp) and filename


def sanitize_filename(filename):
    """Sanitize the filename to prevent path issues"""
    filename = os.path.basename(filename)
    # Replace problematic characters
    filename = filename.replace('\\', '_').replace('/', '_')
    # Windows reserved characters
    for char in ['<', '>', ':', '"', '|', '?', '*']:
        filename = filename.replace(char, '_')
    return filename


def get_user_container_name(user):
    """Generate container name by hashing combined username and timestamp"""
    if not user or not user.username:
        raise ValueError("User must have a valid username")

    # Get current timestamp
    timestamp = str(int(datetime.now().timestamp()))

    # Combine username and timestamp
    combined_string = f"{user.username}-{timestamp}"

    # Generate SHA256 hash of the combined string
    combined_hash = hashlib.sha256(combined_string.encode()).hexdigest()[:16]
    return combined_hash


def create_user_container(user):
    """Create a container for the user if it doesn't exist"""
    container_name = get_user_container_name(user)
    url = f"{STORAGE_BASE_URL}{container_name}"
    headers = {'X-Auth-Token': AUTH_TOKEN}

    try:
        response = requests.put(url, headers=headers, verify=False)  # Disable SSL verify for demo
        if response.status_code not in [201, 202]:
            return False, f"Container creation failed: {response.text}"
        return True, container_name
    except Exception as e:
        return False, str(e)


def upload_to_user_container(file_path, container_name, file_name, content_type='application/octet-stream'):
    """Upload file to user's container"""
    url = f"{STORAGE_BASE_URL}{container_name}/{file_name}"
    headers = {
        'X-Auth-Token': AUTH_TOKEN,
        'Content-Type': content_type
    }

    try:
        with open(file_path, 'rb') as file:
            response = requests.put(url, headers=headers, data=file, verify=False)
            response.raise_for_status()
        return True, url
    except Exception as e:
        return False, str(e)


@csrf_exempt
def upload_dataset(request):
    try:
        if request.method != 'POST':
            return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

        if request.GET.get('finalize') == 'true':
            return finalize_upload(request)

        # Chunk upload handling
        file_chunk = request.FILES.get('file')
        if not file_chunk:
            return JsonResponse({'status': 'error', 'message': 'No file chunk received'}, status=400)

        chunk_number = int(request.POST.get('chunkNumber', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        file_name = sanitize_filename(request.POST.get('fileName', ''))
        file_size = int(request.POST.get('fileSize', 0))

        # First chunk handling
        if chunk_number == 0:
            if not file_name:
                return JsonResponse({'status': 'error', 'message': 'Filename required'}, status=400)

            upload_id = f"{datetime.now().timestamp()}-{file_name}"
            try:
                metadata = json.loads(request.POST.get('metadata', '{}'))
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid metadata format'}, status=400)

            upload_tracker[upload_id] = {
                'file_name': file_name,
                'file_size': file_size,
                'total_chunks': total_chunks,
                'chunks_received': set(),
                'metadata': metadata,
                'temp_files': [],
                'created_at': datetime.now()
            }

        # Validate upload session
        if not validate_upload_id(upload_id) or upload_id not in upload_tracker:
            return JsonResponse({'status': 'error', 'message': 'Invalid upload ID'}, status=400)

        # Check for duplicate chunks
        if chunk_number in upload_tracker[upload_id]['chunks_received']:
            return JsonResponse({'status': 'error', 'message': 'Duplicate chunk'}, status=400)

        # Save chunk locally (temporarily)
        chunk_dir = f"uploads/temp/{upload_id}"
        chunk_path = f"{chunk_dir}/chunk_{chunk_number}"

        try:
            saved_path = default_storage.save(chunk_path, ContentFile(file_chunk.read()))
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Chunk save failed: {str(e)}'}, status=500)

        # Update tracker
        upload_tracker[upload_id]['chunks_received'].add(chunk_number)
        upload_tracker[upload_id]['temp_files'].append(saved_path)

        return JsonResponse({
            'status': 'success',
            'upload_id': upload_id,
            'received_chunks': sorted(upload_tracker[upload_id]['chunks_received'])
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def finalize_upload(request):
    try:
        upload_id = request.GET.get('uploadId')
        if not validate_upload_id(upload_id) or upload_id not in upload_tracker:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid upload ID',
                'code': 'INVALID_UPLOAD_ID',
                'originalUploadId': upload_id if upload_id else None
            }, status=400)

        upload_info = upload_tracker[upload_id]
        clean_upload_id = upload_id.split('-')[0]  # Extract timestamp part

        # Verify all chunks were received
        expected_chunks = set(range(upload_info['total_chunks']))
        if upload_info['chunks_received'] != expected_chunks:
            missing = expected_chunks - upload_info['chunks_received']
            cleanup_upload(upload_id)
            return JsonResponse({
                'status': 'error',
                'message': f'Missing chunks: {sorted(missing)}',
                'code': 'MISSING_CHUNKS',
                'originalUploadId': upload_id,
                'cleanUploadId': clean_upload_id,
                'received': sorted(upload_info['chunks_received']),
                'expected': sorted(expected_chunks)
            }, status=400)

        # Reassemble file locally first
        final_dir = os.path.join("uploads", datetime.now().strftime('%Y'),
                                 datetime.now().strftime('%m'),
                                 datetime.now().strftime('%d'))
        final_path = os.path.join(final_dir, upload_info['file_name'])

        try:
            os.makedirs(os.path.dirname(default_storage.path(final_path)), exist_ok=True)
            with default_storage.open(final_path, 'wb') as final_file:
                for i in range(upload_info['total_chunks']):
                    chunk_path = os.path.join("uploads", "temp", upload_id, f"chunk_{i}")
                    with default_storage.open(chunk_path, 'rb') as chunk_file:
                        final_file.write(chunk_file.read())
        except Exception as assembly_error:
            cleanup_upload(upload_id)
            return JsonResponse({
                'status': 'error',
                'message': f'File assembly failed: {str(assembly_error)}',
                'code': 'FILE_ASSEMBLY_FAILED',
                'originalUploadId': upload_id,
                'cleanUploadId': clean_upload_id
            }, status=500)

        # Create user container
        container_success, container_result = create_user_container(request.user)
        if not container_success:
            cleanup_upload(upload_id)
            if default_storage.exists(final_path):
                default_storage.delete(final_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Container creation failed: {container_result}',
                'code': 'CONTAINER_CREATION_FAILED',
                'originalUploadId': upload_id,
                'cleanUploadId': clean_upload_id
            }, status=500)

        # Upload to user's container
        local_file_path = default_storage.path(final_path)
        upload_success, upload_result = upload_to_user_container(
            local_file_path,
            container_result,
            upload_info['file_name']
        )

        if not upload_success:
            cleanup_upload(upload_id)
            if default_storage.exists(final_path):
                default_storage.delete(final_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Cloud upload failed: {upload_result}',
                'code': 'CLOUD_UPLOAD_FAILED',
                'originalUploadId': upload_id,
                'cleanUploadId': clean_upload_id,
                'container': container_result
            }, status=500)

        # Prepare the download link information

        file_urls = []
        total_files_count = 0

        download_link = {
            "url": upload_result,
            "size": upload_info['file_size'],
            "size_human": sizeof_fmt(upload_info['file_size'])
        }
        file_urls.append(download_link)
        total_files_count = len(file_urls)
        # Create database record
        try:
            with transaction.atomic():
                metadata = upload_info['metadata']
                dataset = Dataset.objects.create(
                    user=request.user,
                    code=container_result,
                    name=metadata.get('dataset_name'),
                    owner=metadata.get('dataset_owner'),
                    language=metadata.get('dataset_language'),
                    license=metadata.get('dataset_license'),
                    format=metadata.get('dataset_format'),
                    desc=metadata.get('dataset_desc'),
                    dataset_tags=metadata.get('dataset_tags'),
                    columnDataType=metadata.get('dataset_columnDataType'),
                    downloadLink=file_urls,
                    filesCount=total_files_count,
                    size=upload_info['file_size']
                )

                if metadata.get('dataset_tags'):
                    tags = [t.strip() for t in metadata['dataset_tags'].split(',') if t.strip()]
                    dataset.tags.set(tags)
        except Exception as db_error:
            cleanup_upload(upload_id)
            if default_storage.exists(final_path):
                default_storage.delete(final_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Database error: {str(db_error)}',
                'code': 'DATABASE_ERROR',
                'originalUploadId': upload_id,
                'cleanUploadId': clean_upload_id
            }, status=500)

        # Cleanup
        cleanup_upload(upload_id)
        if default_storage.exists(final_path):
            default_storage.delete(final_path)

        return JsonResponse({
            'status': 'success',
            'download_link': download_link,
            'dataset_id': dataset.id,
            'metadata': metadata,
            'originalUploadId': upload_id,
            'cleanUploadId': clean_upload_id,
            'container': container_result
        })

    except Exception as unexpected_error:
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(unexpected_error)}',
            'code': 'UNEXPECTED_ERROR',
            'originalUploadId': request.GET.get('uploadId', 'unknown'),
            'cleanUploadId': request.GET.get('uploadId', 'unknown').split('-')[0]
        }, status=500)


def sizeof_fmt(num, suffix='B'):
    """Convert bytes to human-readable format"""
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Y', suffix)


def cleanup_upload(upload_id):
    """Clean up temporary files and tracker entry"""
    if upload_id in upload_tracker:
        for chunk_path in upload_tracker[upload_id]['temp_files']:
            if default_storage.exists(chunk_path):
                default_storage.delete(chunk_path)
        del upload_tracker[upload_id]

###################################################
###################################################
# download from file from cloud storage
###################################################

@login_required
def download_file_from_cloud1(request, pk):
    ACCOUNT = 'AUTH_aiahr-ae5aa48e'
    AUTH_TOKEN = '391af3cea0e0248b92ad2d2671d4eaa8669854be'

    dataset = get_object_or_404(Dataset, id=pk, file_number=file_number )


    # download_url = f'https://storage.aiahura.com/v1/{ACCOUNT}/{container_name}/{file_name}'
    download_url = dataset.downloadLink
    auth_token = AUTH_TOKEN

    try:
        response = requests.get(
            download_url,
            headers={'X-Auth-Token': auth_token},
            stream=True
        )
        response.raise_for_status()

        # Create Django response
        django_response = HttpResponse(
            response.content,
            content_type=response.headers.get('Content-Type')
        )

        # Set content disposition for download
        django_response['Content-Disposition'] = f'attachment; filename="{dataset.code}"'
        return django_response

    except requests.exceptions.RequestException as e:
        # Handle errors (redirect or show error page)
        return HttpResponseRedirect('/download-error/')


@login_required
def download_file_from_cloud(request):
    AUTH_TOKEN = '391af3cea0e0248b92ad2d2671d4eaa8669854be'
    file_url = request.GET.get('file_url')

    if not file_url:
        return HttpResponseRedirect('/download-error/')

    try:
        response = requests.get(
            file_url,
            headers={'X-Auth-Token': AUTH_TOKEN},
            stream=True
        )
        response.raise_for_status()

        # Get file size for progress calculation
        file_size = int(response.headers.get('content-length', 0))
        filename = file_url.split('/')[-1]

        # Create streaming response
        response = HttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('Content-Type', 'application/octet-stream')
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = file_size

        return response

    except requests.exceptions.RequestException as e:
        return HttpResponseRedirect('/download-error/')


###################################################
# Load model for comment sentiment analyzer
###################################################

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

MODEL_PATH = "assets/models/sentiments/HooshvareLab"

# Cache model and tokenizer to avoid redundant loading
_model, _tokenizer, _pipeline = None, None, None

def load_model():
    global _model, _tokenizer, _pipeline
    if _pipeline is None:  # Load the model only if it's not already loaded
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        _pipeline = pipeline("sentiment-analysis", model=_model, tokenizer=_tokenizer)
    return _pipeline

def analyze_sentiment(comment):
    sentiment_pipeline = load_model()
    result = sentiment_pipeline(comment)[0]
    return result["label"], round(result["score"], 2)