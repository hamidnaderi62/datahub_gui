from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import Dataset, User, Comment, PredefinedTag, Request, AnnotationRequest, AnnotationResponse
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
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
from django.core.exceptions import PermissionDenied

import re
import requests
import hashlib
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Dataset
import boto3
from botocore.client import Config
import uuid
import tempfile
import ssl
import urllib3
from botocore.exceptions import ClientError

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def dataset_list_fa(request):
    DATASETS_PER_PAGE = 15
    q = request.GET.get('q')
    all_datasets = Dataset.objects.all()
    if q:
        all_datasets = all_datasets.filter(dataset_tags__icontains=q)
    all_datasets = all_datasets.order_by('-id')
    paginator = Paginator(all_datasets, DATASETS_PER_PAGE)
    page_number = request.GET.get('page')
    try:
        datasets = paginator.get_page(page_number)
    except PageNotAnInteger:
        datasets = paginator.get_page(1)
    except EmptyPage:
        datasets = paginator.get_page(paginator.num_pages)
    return render(request, 'dataset/dataset_list_fa.html', {'datasets': datasets})


def dataset_detail_fa(request, pk=None):
    dataset = get_object_or_404(Dataset.objects.prefetch_related('tags'), id=pk)
    tags = dataset.tags.all()
    similar_datasets = (
        Dataset.objects.filter(tags__in=tags)
        .exclude(id=dataset.id)
        .annotate(num_common_tags=Count('tags'))
        .order_by('-num_common_tags')[:3]
    )

    if request.method == "POST":
        if 'submit_dataset_comment' in request.POST:
            text = request.POST.get('text', '').strip()
            if text:
                label, score = analyze_sentiment(text)
                Comment.objects.create(
                    text=text, dataset=dataset,
                    user=request.user, sentiment_label=label, sentiment_score=score
                )
        elif 'submit_dataset_request' in request.POST:
            Request.objects.create(dataset=dataset, user=request.user)
        elif 'submit_dataset_viewer' in request.POST:
            try:
                df = pd.read_csv(dataset.file.path)
                html_obj = pyg.walk(df[:10], return_html=True)
                return render(request, 'dataset/dataset_detail_fa.html',
                              {'dataset': dataset, 'similar_datasets': similar_datasets, 'html_obj': html_obj})
            except FileNotFoundError:
                raise PermissionDenied("Dataset file not found.")

    return render(request, 'dataset/dataset_detail_fa.html',
                  {'dataset': dataset, 'similar_datasets': similar_datasets})


@login_required
def dataset_download_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    return render(request, 'dataset/dataset_download_fa.html', context={'dataset': dataset})


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
    if is_ajax and request.method == 'POST':
        data = json.load(request)
        dataset = data.get('dataset')
        dataset_name = dataset['dataset_name']
        dataset_owner = dataset['dataset_owner']
        dataset_language = dataset['dataset_language']
        dataset_license = dataset['dataset_license']
        dataset_format = dataset['dataset_format']
        dataset_desc = dataset['dataset_desc']
        dataset_tags = dataset['dataset_tags']
        dataset_columnDataType = dataset['dataset_columnDataType']

        new_dataset = Dataset.objects.create(
            user=request.user,
            name=dataset_name,
            owner=dataset_owner,
            language=dataset_language,
            license=dataset_license,
            format=dataset_format,
            recordsNum=dataset.get('dataset_recordsNum', 0),
            price=dataset.get('dataset_price', 0),
            requestRequired=dataset.get('dataset_requestRequired', False),
            desc=dataset_desc,
            dataset_tags=dataset_tags,
            columnDataType=dataset_columnDataType,
            datasetDate=datetime.now()
        )
        input_tags = dataset_tags.split(",")
        new_dataset.tags.set(input_tags)
    return render(request, 'dataset/dataset_define_stepper_fa.html', context={})


###################################################
# S3 Client Configuration - FIXED VERSION
###################################################

def get_s3_client():
    """Initialize S3 client with workaround for XAmzContentSHA256Mismatch"""
    # Create a custom session to handle SSL issues
    session = boto3.Session()

    client = session.client(
        's3',
        endpoint_url=settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT'],
        aws_access_key_id=settings.CLOUD_STORAGE_CONFIG['ACCESS_KEY'],
        aws_secret_access_key=settings.CLOUD_STORAGE_CONFIG['SECRET_KEY'],
        region_name=settings.CLOUD_STORAGE_CONFIG.get('REGION', 'us-east-1'),
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            retries={'max_attempts': 3, 'mode': 'standard'}
        ),
        verify=False  # Disable SSL verification
    )
    return client


def get_s3_resource():
    """Get S3 resource for alternative upload methods"""
    session = boto3.Session()
    return session.resource(
        's3',
        endpoint_url=settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT'],
        aws_access_key_id=settings.CLOUD_STORAGE_CONFIG['ACCESS_KEY'],
        aws_secret_access_key=settings.CLOUD_STORAGE_CONFIG['SECRET_KEY'],
        region_name=settings.CLOUD_STORAGE_CONFIG.get('REGION', 'us-east-1'),
        verify=False
    )


def create_user_bucket(user):
    """Create a bucket for the user"""
    s3_client = get_s3_client()
    bucket_name = get_user_bucket_name(user)

    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True, bucket_name
    except:
        try:
            # Simple bucket creation without complex configuration
            s3_client.create_bucket(Bucket=bucket_name)
            # Wait briefly for bucket to be ready
            import time
            time.sleep(1)
            return True, bucket_name
        except Exception as e:
            print(f"Bucket creation error: {str(e)}")
            return False, str(e)


def get_user_bucket_name(user):
    """Generate bucket name"""
    if not user or not user.username:
        raise ValueError("User must have a valid username")

    timestamp = str(int(datetime.now().timestamp()))
    combined_string = f"{user.username}-{timestamp}"
    combined_hash = hashlib.sha256(combined_string.encode()).hexdigest()[:16]
    bucket_name = f"user-{combined_hash}".lower()
    return bucket_name


def upload_to_user_bucket(file_path, bucket_name, file_name):
    """Upload file using multiple strategies to avoid XAmzContentSHA256Mismatch"""

    # Strategy 1: Try using requests directly (most reliable for MinIO)
    success, result = upload_via_requests(file_path, bucket_name, file_name)
    if success:
        return True, result

    # Strategy 2: Try using boto3 with different methods
    success, result = upload_via_boto3_multiple(file_path, bucket_name, file_name)
    if success:
        return True, result

    return False, "All upload strategies failed"


def upload_via_requests(file_path, bucket_name, file_name):
    """Upload using direct HTTP requests - most reliable for MinIO"""
    try:
        with open(file_path, 'rb') as f:
            file_content = f.read()

        # Generate presigned URL for PUT
        s3_client = get_s3_client()
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_name,
                'ContentType': get_content_type(file_name)
            },
            ExpiresIn=3600
        )

        # Upload using requests
        response = requests.put(
            presigned_url,
            data=file_content,
            headers={'Content-Type': get_content_type(file_name)},
            verify=False  # Disable SSL verification
        )

        if response.status_code in [200, 204]:
            file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
            return True, file_url
        else:
            return False, f"HTTP {response.status_code}: {response.text}"

    except Exception as e:
        return False, f"Requests upload failed: {str(e)}"


def upload_via_boto3_multiple(file_path, bucket_name, file_name):
    """Try multiple boto3 upload methods"""
    methods = [
        upload_via_boto3_put_object,
        upload_via_boto3_upload_fileobj,
        upload_via_boto3_resource
    ]

    for method in methods:
        success, result = method(file_path, bucket_name, file_name)
        if success:
            return True, result

    return False, "All boto3 methods failed"


def upload_via_boto3_put_object(file_path, bucket_name, file_name):
    """Upload using put_object with chunked reading"""
    try:
        s3_client = get_s3_client()

        # Read file in chunks to avoid memory issues
        with open(file_path, 'rb') as file_data:
            response = s3_client.put_object(
                Bucket=bucket_name,
                Key=file_name,
                Body=file_data,
                ContentType=get_content_type(file_name),
                ContentDisposition=f'attachment; filename="{file_name}"'
            )

        if response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
            file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
            return True, file_url
        else:
            return False, "PutObject failed"

    except Exception as e:
        return False, f"PutObject failed: {str(e)}"


def upload_via_boto3_upload_fileobj(file_path, bucket_name, file_name):
    """Upload using upload_fileobj"""
    try:
        s3_client = get_s3_client()

        with open(file_path, 'rb') as file_data:
            s3_client.upload_fileobj(
                file_data,
                bucket_name,
                file_name,
                ExtraArgs={
                    'ContentType': get_content_type(file_name),
                    'ContentDisposition': f'attachment; filename="{file_name}"'
                }
            )

        file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
        return True, file_url

    except Exception as e:
        return False, f"UploadFileObj failed: {str(e)}"


def upload_via_boto3_resource(file_path, bucket_name, file_name):
    """Upload using S3 resource"""
    try:
        s3_resource = get_s3_resource()
        bucket = s3_resource.Bucket(bucket_name)

        with open(file_path, 'rb') as file_data:
            bucket.put_object(
                Key=file_name,
                Body=file_data,
                ContentType=get_content_type(file_name),
                ContentDisposition=f'attachment; filename="{file_name}"'
            )

        file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
        return True, file_url

    except Exception as e:
        return False, f"S3 resource upload failed: {str(e)}"


def get_content_type(filename):
    """Determine content type based on file extension"""
    extension = os.path.splitext(filename)[1].lower()
    content_types = {
        '.csv': 'text/csv',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.parquet': 'application/octet-stream',
        '.zip': 'application/zip',
        '.gz': 'application/gzip',
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    return content_types.get(extension, 'application/octet-stream')


def generate_presigned_url(bucket_name, object_key, expiration=3600):
    """Generate presigned URL for temporary access"""
    s3_client = get_s3_client()
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key
            },
            ExpiresIn=expiration
        )
        return True, url
    except Exception as e:
        return False, str(e)


# Upload tracking
upload_tracker = {}


def validate_upload_id(upload_id):
    if not upload_id:
        return False
    parts = upload_id.split('-', 1)
    if len(parts) != 2:
        return False
    timestamp, filename = parts
    return re.match(r'^\d+\.\d+$', timestamp) and filename


def sanitize_filename(filename):
    filename = os.path.basename(filename)
    filename = filename.replace('\\', '_').replace('/', '_')
    for char in ['<', '>', ':', '"', '|', '?', '*']:
        filename = filename.replace(char, '_')
    return filename


@csrf_exempt
def upload_dataset(request):
    try:
        if request.method != 'POST':
            return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

        if request.GET.get('finalize') == 'true':
            return finalize_upload(request)

        file_chunk = request.FILES.get('file')
        if not file_chunk:
            return JsonResponse({'status': 'error', 'message': 'No file chunk received'}, status=400)

        chunk_number = int(request.POST.get('chunkNumber', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        file_name = sanitize_filename(request.POST.get('fileName', ''))
        file_size = int(request.POST.get('fileSize', 0))

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

        if not validate_upload_id(upload_id) or upload_id not in upload_tracker:
            return JsonResponse({'status': 'error', 'message': 'Invalid upload ID'}, status=400)

        if chunk_number in upload_tracker[upload_id]['chunks_received']:
            return JsonResponse({'status': 'error', 'message': 'Duplicate chunk'}, status=400)

        chunk_dir = f"uploads/temp/{upload_id}"
        chunk_path = f"{chunk_dir}/chunk_{chunk_number}"

        try:
            saved_path = default_storage.save(chunk_path, ContentFile(file_chunk.read()))
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Chunk save failed: {str(e)}'}, status=500)

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
            }, status=400)

        upload_info = upload_tracker[upload_id]

        expected_chunks = set(range(upload_info['total_chunks']))
        if upload_info['chunks_received'] != expected_chunks:
            missing = expected_chunks - upload_info['chunks_received']
            cleanup_upload(upload_id)
            return JsonResponse({
                'status': 'error',
                'message': f'Missing chunks: {sorted(missing)}',
                'code': 'MISSING_CHUNKS',
            }, status=400)

        final_dir = os.path.join("uploads", datetime.now().strftime('%Y'),
                                 datetime.now().strftime('%m'),
                                 datetime.now().strftime('%d'))
        final_path = os.path.join(final_dir, upload_info['file_name'])

        try:
            os.makedirs(os.path.dirname(default_storage.path(final_path)), exist_ok=True)
            with open(default_storage.path(final_path), 'wb') as final_file:
                for i in range(upload_info['total_chunks']):
                    chunk_path = os.path.join("uploads", "temp", upload_id, f"chunk_{i}")
                    with open(default_storage.path(chunk_path), 'rb') as chunk_file:
                        final_file.write(chunk_file.read())
        except Exception as assembly_error:
            cleanup_upload(upload_id)
            return JsonResponse({
                'status': 'error',
                'message': f'File assembly failed: {str(assembly_error)}',
                'code': 'FILE_ASSEMBLY_FAILED',
            }, status=500)

        assembled_path = default_storage.path(final_path)
        if not os.path.exists(assembled_path):
            cleanup_upload(upload_id)
            return JsonResponse({
                'status': 'error',
                'message': 'Assembled file not found',
                'code': 'FILE_NOT_FOUND',
            }, status=500)

        assembled_size = os.path.getsize(assembled_path)
        if assembled_size != upload_info['file_size']:
            cleanup_upload(upload_id)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({
                'status': 'error',
                'message': f'File size mismatch: expected {upload_info["file_size"]}, got {assembled_size}',
                'code': 'FILE_SIZE_MISMATCH',
            }, status=400)

        bucket_success, bucket_result = create_user_bucket(request.user)
        if not bucket_success:
            cleanup_upload(upload_id)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Bucket creation failed: {bucket_result}',
                'code': 'BUCKET_CREATION_FAILED',
            }, status=500)

        upload_success, upload_result = upload_to_user_bucket(
            assembled_path,
            bucket_result,
            upload_info['file_name']
        )

        if not upload_success:
            cleanup_upload(upload_id)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Cloud upload failed: {upload_result}',
                'code': 'CLOUD_UPLOAD_FAILED',
            }, status=500)

        download_link = {
            "url": '', # didnt need url
            "bucket_name": bucket_result,
            "object_key": upload_info['file_name'],
            "size": upload_info['file_size'],
            "size_human": sizeof_fmt(upload_info['file_size'])
        }

        try:
            with transaction.atomic():
                metadata = upload_info['metadata']
                dataset = Dataset.objects.create(
                    user=request.user,
                    code=bucket_result,
                    name=metadata.get('dataset_name', ''),
                    owner=metadata.get('dataset_owner', ''),
                    language=metadata.get('dataset_language', ''),
                    license=metadata.get('dataset_license', ''),
                    format=metadata.get('dataset_format', ''),
                    recordsNum=metadata.get('dataset_recordsNum', 0),
                    price=float(metadata.get('dataset_price', 0)),
                    requestRequired=metadata.get('dataset_requestRequired', False),
                    desc=metadata.get('dataset_desc', ''),
                    dataset_tags=metadata.get('dataset_tags', ''),
                    columnDataType=metadata.get('dataset_columnDataType', ''),
                    downloadLink=[download_link],
                    filesCount=1,
                    size=upload_info['file_size']
                )

                if metadata.get('dataset_tags'):
                    tags = [t.strip() for t in metadata['dataset_tags'].split(',') if t.strip()]
                    dataset.tags.set(tags)

        except Exception as db_error:
            cleanup_upload(upload_id)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({
                'status': 'error',
                'message': f'Database error: {str(db_error)}',
                'code': 'DATABASE_ERROR',
            }, status=500)

        cleanup_upload(upload_id)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)

        return JsonResponse({
            'status': 'success',
            'download_link': download_link,
            'dataset_id': dataset.id,
            'metadata': metadata,
            'bucket': bucket_result
        })

    except Exception as unexpected_error:
        import traceback
        error_details = traceback.format_exc()
        print(f"Unexpected error in finalize_upload: {error_details}")
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(unexpected_error)}',
            'code': 'UNEXPECTED_ERROR',
        }, status=500)


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Y', suffix)


def cleanup_upload(upload_id):
    if upload_id in upload_tracker:
        for chunk_path in upload_tracker[upload_id]['temp_files']:
            if default_storage.exists(chunk_path):
                default_storage.delete(chunk_path)
        del upload_tracker[upload_id]


# Rest of the code remains the same for Dataset Viewer, Annotation, etc.
# [Include the Dataset Viewer, Annotation, and other functions from your original code]

###################################################
# Dataset Viewer
###################################################
import requests
import tempfile
import os
import pandas as pd
import math
from django.views.generic import TemplateView
from django.utils.safestring import mark_safe
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.conf import settings
import pygwalker as pyg
from .models import Dataset


class MyPygWalkerView1(TemplateView):
    template_name = "dataset/dataset_viewer_fa.html"

    def get_download_info(self, download_links, file_index=0):
        """Extract file info from dataset's downloadLink by index"""
        try:
            if download_links and isinstance(download_links, list) and file_index < len(download_links):
                return download_links[file_index]
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing downloadLink: {str(e)}")
            return None

    def download_file_from_s3(self, bucket_name, object_key):
        """Download file from S3 using presigned URL and return temporary file path"""
        try:
            # Generate fresh presigned URL
            success, presigned_url = generate_presigned_url(bucket_name, object_key, 3600)
            if not success:
                print(f"Failed to generate presigned URL for {bucket_name}/{object_key}")
                return None

            # Download using requests from the presigned URL
            response = requests.get(presigned_url, stream=True, timeout=30)
            response.raise_for_status()

            # Extract file extension
            file_ext = object_key.split('.')[-1].lower() if '.' in object_key else 'bin'

            print(f"Downloading file from S3: {object_key}")

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name

        except requests.exceptions.RequestException as e:
            print(f"Error downloading file from S3: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error during download: {str(e)}")
            return None

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
            elif file_ext == 'xlsx' or file_ext == 'xls':
                return pd.read_excel(file_path)
            elif file_ext == 'json':
                return pd.read_json(file_path)
            else:  # default to CSV
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {str(e)}")
            return pd.DataFrame()

    def sample_dataframe(self, df):
        """Take 10% sample of dataframe (max 100 rows)"""
        if df.empty:
            return df

        sample_size = min(100, max(1, math.ceil(len(df) * 0.1)))
        return df.sample(n=sample_size, random_state=42)

    def get_file_info_list(self, download_links):
        """Get list of file information for navigation"""
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })
        return file_list

    def get_supported_extensions(self):
        """Return list of supported file extensions"""
        return ['csv', 'parquet', 'xlsx', 'xls', 'json']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dataset_id = self.request.GET.get('dataset_id')
        file_index = int(self.request.GET.get('file_index', -1))  # Default to -1 (no file selected)

        if not dataset_id:
            context['error'] = "No dataset ID provided"
            return context

        try:
            dataset = Dataset.objects.get(id=dataset_id)
            context['dataset'] = dataset

            # Get download links info (contains bucket_name and object_key)
            download_links = dataset.downloadLink
            context['file_count'] = len(download_links) if download_links else 0
            context['current_file_index'] = file_index

            # Get file list for navigation
            context['file_list'] = self.get_file_info_list(download_links)
            context['supported_extensions'] = self.get_supported_extensions()

            if not download_links:
                context['error'] = "No files available for this dataset"
                return context

            # Only process file data if a file is selected
            if file_index >= 0 and file_index < len(download_links):
                # Get specific file info by index
                file_info = self.get_download_info(download_links, file_index)
                if not file_info:
                    context['error'] = f"File index {file_index} not found"
                    return context

                bucket_name = file_info.get('bucket_name')
                object_key = file_info.get('object_key')

                if not bucket_name or not object_key:
                    context['error'] = "Missing bucket name or object key"
                    return context

                # Check if file format is supported
                file_extension = object_key.split('.')[-1].lower() if '.' in object_key else ''
                supported_extensions = self.get_supported_extensions()

                if file_extension not in supported_extensions:
                    context[
                        'error'] = f"File format '{file_extension}' is not supported for viewing. Supported formats: {', '.join(supported_extensions)}"
                    context['current_filename'] = object_key.split('/')[-1]
                    context['current_file_extension'] = file_extension
                    return context

                # Download the file using bucket_name and object_key
                tmp_file_path = self.download_file_from_s3(bucket_name, object_key)
                if not tmp_file_path:
                    context['error'] = "Could not download file from S3"
                    return context

                # Read the downloaded file
                df = self.read_data_file(tmp_file_path)

                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    print(f"Error cleaning up temp file: {e}")

                if df.empty:
                    context['error'] = "Could not load dataset or dataset is empty"
                    context['current_filename'] = object_key.split('/')[-1]
                else:
                    sampled_df = self.sample_dataframe(df)
                    pyg_html = pyg.walk(
                        sampled_df,
                        spec=self.get_pygwalker_config(),
                        return_html=True
                    )
                    context['pygwalker_html'] = mark_safe(pyg_html)
                    context['row_count'] = len(df)
                    context['sample_count'] = len(sampled_df)
                    context['current_filename'] = object_key.split('/')[-1]
                    context['current_file_extension'] = file_extension
                    context['columns_count'] = len(df.columns)
                    context['columns_list'] = list(df.columns)

        except Dataset.DoesNotExist:
            context['error'] = "Dataset not found"
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            context['error'] = f"An unexpected error occurred: {str(e)}"

        return context


class MyPygWalkerView(TemplateView):
    template_name = "dataset/dataset_viewer_fa.html"

    def get_download_info(self, download_links, file_index=0):
        """Extract file info from dataset's downloadLink by index"""
        try:
            if download_links and isinstance(download_links, list) and file_index < len(download_links):
                return download_links[file_index]
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing downloadLink: {str(e)}")
            return None

    def download_file_from_s3(self, bucket_name, object_key):
        """Download file from S3 using presigned URL and return temporary file path"""
        try:
            # Generate fresh presigned URL
            success, presigned_url = generate_presigned_url(bucket_name, object_key, 3600)
            if not success:
                print(f"Failed to generate presigned URL for {bucket_name}/{object_key}")
                return None

            # Download using requests from the presigned URL
            response = requests.get(presigned_url, stream=True, timeout=30)
            response.raise_for_status()

            # Extract file extension
            file_ext = object_key.split('.')[-1].lower() if '.' in object_key else 'bin'

            print(f"Downloading file from S3: {object_key}")

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name

        except requests.exceptions.RequestException as e:
            print(f"Error downloading file from S3: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error during download: {str(e)}")
            return None

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
            elif file_ext == 'xlsx' or file_ext == 'xls':
                return pd.read_excel(file_path)
            elif file_ext == 'json':
                return pd.read_json(file_path)
            else:  # default to CSV
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {str(e)}")
            return pd.DataFrame()

    def sample_dataframe(self, df):
        """Take 10% sample of dataframe (max 100 rows)"""
        if df.empty:
            return df

        sample_size = min(100, max(1, math.ceil(len(df) * 0.1)))
        return df.sample(n=sample_size, random_state=42)

    def get_file_info_list(self, download_links):
        """Get list of file information for navigation"""
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })
        return file_list

    def get_supported_extensions(self):
        """Return list of supported file extensions"""
        return ['csv', 'parquet', 'xlsx', 'xls', 'json']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dataset_id = self.request.GET.get('dataset_id')
        file_index = int(self.request.GET.get('file_index', -1))

        if not dataset_id:
            context['error'] = "No dataset ID provided"
            return context

        try:
            dataset = Dataset.objects.get(id=dataset_id)
            context['dataset'] = dataset

            # Get download links info
            download_links = dataset.downloadLink
            context['file_count'] = len(download_links) if download_links else 0
            context['current_file_index'] = file_index

            # Get file list for navigation
            context['file_list'] = self.get_file_info_list(download_links)
            context['supported_extensions'] = self.get_supported_extensions()

            if not download_links:
                context['error'] = "No files available for this dataset"
                return context

            # Only process file data if a file is selected
            if file_index >= 0 and file_index < len(download_links):
                # Get specific file info by index
                file_info = self.get_download_info(download_links, file_index)
                if not file_info:
                    context['error'] = f"File index {file_index} not found"
                    return context

                bucket_name = file_info.get('bucket_name')
                object_key = file_info.get('object_key')

                if not bucket_name or not object_key:
                    context['error'] = "Missing bucket name or object key"
                    return context

                # Store current file info for template
                context['current_file_info'] = file_info
                context['current_filename'] = object_key.split('/')[-1]
                context['current_file_extension'] = object_key.split('.')[-1].lower() if '.' in object_key else ''

                # Check if file format is supported
                supported_extensions = self.get_supported_extensions()
                if context['current_file_extension'] not in supported_extensions:
                    context[
                        'error'] = f"File format '{context['current_file_extension']}' is not supported for viewing. Supported formats: {', '.join(supported_extensions)}"
                    return context

                # Download the file using bucket_name and object_key
                tmp_file_path = self.download_file_from_s3(bucket_name, object_key)
                if not tmp_file_path:
                    context['error'] = "Could not download file from S3"
                    return context

                # Read the downloaded file
                df = self.read_data_file(tmp_file_path)

                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    print(f"Error cleaning up temp file: {e}")

                if df.empty:
                    context['error'] = "Could not load dataset or dataset is empty"
                else:
                    sampled_df = self.sample_dataframe(df)
                    pyg_html = pyg.walk(
                        sampled_df,
                        spec=self.get_pygwalker_config(),
                        return_html=True
                    ).to_html()
                    context['pygwalker_html'] = mark_safe(pyg_html)
                    context['row_count'] = len(df)
                    context['sample_count'] = len(sampled_df)
                    context['columns_count'] = len(df.columns)
                    context['columns_list'] = list(df.columns)

        except Dataset.DoesNotExist:
            context['error'] = "Dataset not found"
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            context['error'] = f"An unexpected error occurred: {str(e)}"

        return context


from django.shortcuts import render, get_object_or_404


def dataset_files_fa(request, pk=None):
    dataset_id = pk or request.GET.get('dataset_id')

    if not dataset_id:
        return render(request, 'dataset/dataset_files_fa.html', {'error': 'No dataset ID provided'})

    try:
        dataset = Dataset.objects.get(id=dataset_id)

        # Get download links info
        download_links = dataset.downloadLink
        file_count = len(download_links) if download_links else 0

        # Get file list for navigation
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })

        # Supported extensions for display
        supported_extensions = ['csv', 'parquet', 'xlsx', 'xls', 'json']

        context = {
            'dataset': dataset,
            'file_list': file_list,
            'file_count': file_count,
            'supported_extensions': supported_extensions,
        }

        # Check if a file is selected for preview
        file_index = request.GET.get('file_index')
        if file_index:
            try:
                file_index = int(file_index)
                if file_index >= 0 and file_index < len(download_links):
                    # Use MyPygWalkerView methods to get file preview
                    viewer = MyPygWalkerView()

                    # Get file info
                    file_info = viewer.get_download_info(download_links, file_index)
                    if file_info:
                        context['current_file_index'] = file_index
                        context['current_file_info'] = file_info
                        context['current_filename'] = file_info.get('object_key', '').split('/')[-1]
                        context['current_file_extension'] = file_info.get('object_key', '').split('.')[
                            -1].lower() if '.' in file_info.get('object_key', '') else ''

                        # Only load PygWalker data if file format is supported
                        if context['current_file_extension'] in supported_extensions:
                            # Download and process the file
                            bucket_name = file_info.get('bucket_name')
                            object_key = file_info.get('object_key')

                            if bucket_name and object_key:
                                tmp_file_path = viewer.download_file_from_s3(bucket_name, object_key)
                                if tmp_file_path:
                                    df = viewer.read_data_file(tmp_file_path)

                                    if not df.empty:
                                        sampled_df = viewer.sample_dataframe(df)
                                        pyg_html = pyg.walk(
                                            sampled_df,
                                            spec=viewer.get_pygwalker_config(),
                                            return_html=True
                                        )
                                        context['pygwalker_html'] = mark_safe(pyg_html)
                                        context['row_count'] = len(df)
                                        context['sample_count'] = len(sampled_df)
                                        context['columns_count'] = len(df.columns)
                                        context['columns_list'] = list(df.columns)

                                    # Clean up temporary file
                                    try:
                                        os.unlink(tmp_file_path)
                                    except Exception as e:
                                        print(f"Error cleaning up temp file: {e}")
            except (ValueError, IndexError) as e:
                context['error'] = f"Invalid file index: {file_index}"

        return render(request, 'dataset/dataset_files_fa.html', context)

    except Dataset.DoesNotExist:
        return render(request, 'dataset/dataset_files_fa.html', {'error': 'Dataset not found'})
    except Exception as e:
        print(f"Unexpected error in dataset_files_fa: {str(e)}")
        return render(request, 'dataset/dataset_files_fa.html', {'error': f'An unexpected error occurred: {str(e)}'})
###################################################
# Download dataset file using Presigned URLs
###################################################

@login_required
def download_file_from_cloud(request):
    """
    Serve file through Django to avoid CORS issues
    """
    dataset_id = request.GET.get('dataset_id')
    file_index = int(request.GET.get('file_index', 0))

    if not dataset_id:
        return HttpResponseRedirect('/download-error/')

    try:
        dataset = Dataset.objects.get(id=dataset_id)
        download_links = dataset.downloadLink

        if not download_links or not isinstance(download_links, list):
            return HttpResponseRedirect('/download-error/')

        if file_index >= len(download_links) or file_index < 0:
            return HttpResponseRedirect('/download-error/')

        # Get file info from database
        file_info = download_links[file_index]
        bucket_name = file_info.get('bucket_name')
        object_key = file_info.get('object_key')

        if not bucket_name or not object_key:
            return HttpResponseRedirect('/download-error/')

        # Generate fresh presigned URL
        expiration = 3600  # 1 hour
        success, presigned_url = generate_presigned_url(bucket_name, object_key, expiration)

        if not success:
            return HttpResponseRedirect('/download-error/')

        # Download file content
        response = requests.get(presigned_url, stream=True)
        response.raise_for_status()

        # Get filename from object_key
        filename = object_key.split('/')[-1]

        # Create Django response with file content
        django_response = HttpResponse(
            response.content,
            content_type=response.headers.get('content-type', 'application/octet-stream')
        )

        # Set content disposition for download
        django_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        django_response['Content-Length'] = len(response.content)

        return django_response

    except Dataset.DoesNotExist:
        return HttpResponseRedirect('/download-error/')
    except Exception as e:
        print(f"Download error: {str(e)}")
        return HttpResponseRedirect('/download-error/')


@login_required
def get_file_info(request):
    """
    API endpoint to get file information without downloading
    """
    dataset_id = request.GET.get('dataset_id')

    if not dataset_id:
        return JsonResponse({'error': 'No dataset ID provided'}, status=400)

    try:
        dataset = Dataset.objects.get(id=dataset_id)
        download_links = dataset.downloadLink

        if not download_links or not isinstance(download_links, list):
            return JsonResponse({'error': 'No download links available'}, status=404)

        file_info = download_links[0]  # Get first file info

        return JsonResponse({
            'filename': file_info['url'].split('/')[-1].split('?')[0],
            'size': file_info['size'],
            'size_human': file_info['size_human'],
            'url': file_info['url']
        })

    except Dataset.DoesNotExist:
        return JsonResponse({'error': 'Dataset not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def check_presigned_url_validity(presigned_url):
    """
    Utility function to check if a presigned URL is still valid
    """
    try:
        response = requests.head(presigned_url, timeout=10)
        return response.status_code == 200
    except:
        return False
###################################################
# Annotation Module
###################################################

def dataset_annotation_request_fa(request, pk=None):
    if request.method == 'POST':
        if 'btn_annotation_request_cancel' in request.POST:
            AnnotationRequest.objects.filter(id=request.POST.get('annotation_request_id')).update(
                annotationStatus='Canceled', responseDateTime=datetime.now())

        if 'btn_annotation_response_accept' in request.POST:
            acceptedAnnotationResponse = AnnotationResponse.objects.filter(
                id=request.POST.get('annotation_response_id')).get()
            annotationRequest = AnnotationRequest.objects.filter(
                id=acceptedAnnotationResponse.annotationRequest.id).get()
            totalFinalPrice = annotationRequest.totalRecords * acceptedAnnotationResponse.suggestedPrice

            AnnotationResponse.objects.filter(annotationRequest=acceptedAnnotationResponse.annotationRequest).update(
                responseType='Reject', responseDate=datetime.now())
            AnnotationResponse.objects.filter(id=acceptedAnnotationResponse.id).update(responseType='Accept',
                                                                                       responseDate=datetime.now())
            AnnotationRequest.objects.filter(id=acceptedAnnotationResponse.annotationRequest.id).update(
                annotationStatus='Accepted', finalPrice=acceptedAnnotationResponse.suggestedPrice,
                totalFinalPrice=totalFinalPrice, responseDateTime=datetime.now())

    dataset = get_object_or_404(Dataset, id=pk)
    annotation_requests = AnnotationRequest.objects.filter(dataset=dataset.id).order_by('-requestDateTime')
    annotation_responses = AnnotationResponse.objects.filter(dataset=dataset.id).order_by('-responseDate')
    return render(request, 'dataset/dataset_annotation_request_fa.html',
                  context={'dataset': dataset, 'annotation_requests': annotation_requests,
                           'annotation_responses': annotation_responses})


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
                                             , requestDateTime=datetime.now()
                                             )

            return render(request, 'dataset/dataset_annotation_request_fa.html', context={})


def dataset_annotation_list_fa(request):
    all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').select_related(
        'dataset').order_by('-id')
    if request.method == "GET":
        q = request.GET.get('q')
        print(q)
        if q:
            all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested',
                                                                       tags__icontains=q).select_related(
                'dataset').order_by('-requestDateTime')
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
                                          , responseDate=datetime.now()
                                          )

        all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').order_by(
            '-requestDateTime').select_related('dataset')
    page_number = request.GET.get('page')
    paginator = Paginator(all_annotation_requests, 9)
    annotation_requests = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_annotation_list_fa.html',
                  context={'annotation_requests': annotation_requests})


def dataset_annotation_record_fa(request, pk=None):
    return render(request, 'dataset/dataset_annotation_record_fa.html', context={})


###################################################
# Debug and Test Functions
###################################################

@csrf_exempt
def test_s3_connection(request):
    """Test S3 connection and upload functionality"""
    try:
        s3_client = get_s3_client()

        # Test basic connectivity
        buckets = s3_client.list_buckets()
        bucket_list = [b['Name'] for b in buckets.get('Buckets', [])]

        # Test bucket creation
        test_bucket = "test-bucket-" + str(int(datetime.now().timestamp()))
        s3_client.create_bucket(Bucket=test_bucket)

        # Test file upload
        test_content = b"Hello, World! This is a test file."
        s3_client.put_object(
            Bucket=test_bucket,
            Key="test-file.txt",
            Body=test_content,
            ContentType='text/plain'
        )

        # Test file download
        response = s3_client.get_object(Bucket=test_bucket, Key="test-file.txt")
        downloaded_content = response['Body'].read()

        # Cleanup
        s3_client.delete_object(Bucket=test_bucket, Key="test-file.txt")
        s3_client.delete_bucket(Bucket=test_bucket)

        return JsonResponse({
            'status': 'success',
            'buckets': bucket_list,
            'upload_download_test': 'PASSED',
            'message': 'S3 connection test completed successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'S3 connection test failed: {str(e)}'
        }, status=500)


###################################################
# Temp functions
###################################################
def dataset_ner(request):
    return render(request, 'dataset/dataset_ner.html', context={})


def analyze_sentiment(comment):
    """Dummy sentiment analysis function - replace with actual implementation"""
    # This is a placeholder - implement your actual sentiment analysis here
    return "POSITIVE", 0.95