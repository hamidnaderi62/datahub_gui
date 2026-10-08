"""Staff-facing operations views.

The dashboard intentionally keeps write actions small and auditable: status
changes and user activation are explicit POSTs, while provider imports are
submitted to the connector service and tracked locally by request id.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from dataset.models import (
    Dataset,
    DatasetVersion,
    PipelineRun,
    QualityReport,
)
from marketplace.models import Order

from .models import ProviderImportRequest

User = get_user_model()

TEXT = {
    'en': {
        'title': 'Operations center', 'subtitle': 'Monitor your data exchange platform in one place.',
        'overview': 'Overview', 'datasets': 'Datasets', 'users': 'Users', 'orders': 'Marketplace',
        'imports': 'Provider imports', 'welcome': 'Good to see you, {name}',
        'total_users': 'Total users', 'active_users': 'Active users', 'total_datasets': 'Datasets',
        'published': 'Published', 'attention': 'Needs attention', 'orders_count': 'Orders',
        'revenue': 'Paid volume', 'pipeline': 'Pipeline runs', 'recent_datasets': 'Recent datasets',
        'recent_orders': 'Recent transactions', 'quality_queue': 'Quality queue', 'quick_actions': 'Quick actions',
        'new_import': 'Import from Hugging Face / Kaggle', 'manage_datasets': 'Review datasets',
        'manage_users': 'Manage users', 'manage_orders': 'Review transactions', 'name': 'Dataset',
        'owner': 'Owner', 'status': 'Status', 'created': 'Created', 'action': 'Action',
        'no_rows': 'No records found.', 'search': 'Search', 'all_statuses': 'All statuses',
        'save': 'Save', 'active': 'Active', 'inactive': 'Inactive', 'toggle': 'Change access',
        'provider': 'Provider', 'provider_id': 'Dataset ID', 'import_help': 'Enter the provider ID, for example “org/dataset” for Hugging Face or “owner/dataset” for Kaggle.',
        'submit_import': 'Start import', 'owner_user': 'Platform owner', 'imports_recent': 'Recent provider jobs',
        'refresh': 'Refresh status', 'job': 'Job', 'error': 'Error', 'open_dataset': 'Open dataset',
        'import_started': 'Import job queued successfully.', 'status_saved': 'Dataset status updated.', 'publish_blocked': 'This dataset cannot be published until a quality report exists and does not fail.',
        'user_updated': 'User access updated.', 'api_unavailable': 'The connector service is unavailable. Check DATAHUB_API_IMPORT_URL and the shared HMAC secret.',
        'invalid_provider': 'Choose a supported provider.', 'invalid_id': 'Enter a valid provider dataset ID.',
    },
    'fa': {
        'title': 'مرکز مدیریت', 'subtitle': 'پایش و مدیریت پلتفرم تبادل داده در یک نگاه.', 'overview': 'نمای کلی', 'datasets': 'دیتاست‌ها', 'users': 'کاربران', 'orders': 'بازارچه', 'imports': 'دریافت از سرویس‌ها', 'welcome': 'خوش آمدید، {name}', 'total_users': 'کل کاربران', 'active_users': 'کاربران فعال', 'total_datasets': 'دیتاست‌ها', 'published': 'منتشرشده', 'attention': 'نیازمند توجه', 'orders_count': 'سفارش‌ها', 'revenue': 'حجم پرداخت‌شده', 'pipeline': 'اجراهای پردازش', 'recent_datasets': 'دیتاست‌های اخیر', 'recent_orders': 'تراکنش‌های اخیر', 'quality_queue': 'صف کنترل کیفیت', 'quick_actions': 'دسترسی سریع', 'new_import': 'دریافت از Hugging Face / Kaggle', 'manage_datasets': 'بررسی دیتاست‌ها', 'manage_users': 'مدیریت کاربران', 'manage_orders': 'بررسی تراکنش‌ها', 'name': 'دیتاست', 'owner': 'مالک', 'status': 'وضعیت', 'created': 'ایجاد', 'action': 'عملیات', 'no_rows': 'رکوردی پیدا نشد.', 'search': 'جستجو', 'all_statuses': 'همه وضعیت‌ها', 'save': 'ذخیره', 'active': 'فعال', 'inactive': 'غیرفعال', 'toggle': 'تغییر دسترسی', 'provider': 'سرویس', 'provider_id': 'شناسه دیتاست', 'import_help': 'شناسه را وارد کنید؛ برای Hugging Face مانند org/dataset و برای Kaggle مانند owner/dataset.', 'submit_import': 'شروع دریافت', 'owner_user': 'مالک پلتفرم', 'imports_recent': 'درخواست‌های اخیر', 'refresh': 'به‌روزرسانی وضعیت', 'job': 'وظیفه', 'error': 'خطا', 'open_dataset': 'مشاهده دیتاست', 'import_started': 'وظیفه دریافت با موفقیت در صف قرار گرفت.', 'status_saved': 'وضعیت دیتاست به‌روزرسانی شد.', 'publish_blocked': 'تا زمانی که گزارش کیفیت وجود نداشته باشد یا مردود باشد، انتشار ممکن نیست.', 'user_updated': 'دسترسی کاربر به‌روزرسانی شد.', 'api_unavailable': 'سرویس اتصال در دسترس نیست. تنظیمات DATAHUB_API_IMPORT_URL و کلید مشترک را بررسی کنید.', 'invalid_provider': 'یک سرویس معتبر انتخاب کنید.', 'invalid_id': 'شناسه معتبر دیتاست را وارد کنید.',
    },
    'ar': {
        'title': 'مركز العمليات', 'subtitle': 'راقب منصة تبادل البيانات وأدرها من مكان واحد.', 'overview': 'نظرة عامة', 'datasets': 'مجموعات البيانات', 'users': 'المستخدمون', 'orders': 'السوق', 'imports': 'استيراد خارجي', 'welcome': 'مرحباً، {name}', 'total_users': 'إجمالي المستخدمين', 'active_users': 'المستخدمون النشطون', 'total_datasets': 'مجموعات البيانات', 'published': 'منشورة', 'attention': 'تحتاج إلى مراجعة', 'orders_count': 'الطلبات', 'revenue': 'حجم المدفوعات', 'pipeline': 'عمليات المعالجة', 'recent_datasets': 'أحدث مجموعات البيانات', 'recent_orders': 'أحدث المعاملات', 'quality_queue': 'قائمة فحص الجودة', 'quick_actions': 'إجراءات سريعة', 'new_import': 'استيراد من Hugging Face / Kaggle', 'manage_datasets': 'مراجعة مجموعات البيانات', 'manage_users': 'إدارة المستخدمين', 'manage_orders': 'مراجعة المعاملات', 'name': 'مجموعة البيانات', 'owner': 'المالك', 'status': 'الحالة', 'created': 'الإنشاء', 'action': 'الإجراء', 'no_rows': 'لا توجد سجلات.', 'search': 'بحث', 'all_statuses': 'كل الحالات', 'save': 'حفظ', 'active': 'نشط', 'inactive': 'غير نشط', 'toggle': 'تغيير الوصول', 'provider': 'المصدر', 'provider_id': 'معرّف مجموعة البيانات', 'import_help': 'أدخل المعرّف، مثل org/dataset في Hugging Face أو owner/dataset في Kaggle.', 'submit_import': 'بدء الاستيراد', 'owner_user': 'مالك المنصة', 'imports_recent': 'عمليات الاستيراد الأخيرة', 'refresh': 'تحديث الحالة', 'job': 'المهمة', 'error': 'خطأ', 'open_dataset': 'فتح مجموعة البيانات', 'import_started': 'تم وضع مهمة الاستيراد في قائمة الانتظار.', 'status_saved': 'تم تحديث حالة مجموعة البيانات.', 'publish_blocked': 'لا يمكن النشر حتى يتوفر تقرير جودة ولا تكون نتيجته فاشلة.', 'user_updated': 'تم تحديث وصول المستخدم.', 'api_unavailable': 'خدمة الموصل غير متاحة. تحقق من DATAHUB_API_IMPORT_URL والمفتاح المشترك.', 'invalid_provider': 'اختر مصدراً مدعوماً.', 'invalid_id': 'أدخل معرّفاً صالحاً.',
    },
}


def _text(request):
    language = (getattr(request, 'LANGUAGE_CODE', None) or 'fa').split('-')[0]
    return TEXT.get(language, TEXT['en']), language


def _staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


staff_required = user_passes_test(_staff, login_url='account:login')


def _base_context(request, **extra):
    labels, language = _text(request)
    context = {'labels': labels, 'dashboard_language': language}
    context.update(extra)
    return context


@staff_required
def overview(request):
    attention_q = Q(status__in=['quarantined', 'needs_review', 'failed'])
    paid = Order.objects.filter(status=Order.Status.PAID).aggregate(total=Sum('amount_minor'))['total'] or 0
    since = timezone.now() - timedelta(days=13)
    dataset_by_day = {
        row['day']: row['total']
        for row in Dataset.objects.filter(created__gte=since).annotate(day=TruncDate('created')).values('day').annotate(total=Count('id'))
    }
    order_by_day = {
        row['day']: row['total']
        for row in Order.objects.filter(created_at__gte=since).annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('id'))
    }
    daily = []
    for day in range(14):
        date = (since + timedelta(days=day)).date()
        daily.append({
            'label': date.isoformat()[5:],
            'datasets': dataset_by_day.get(date, 0),
            'orders': order_by_day.get(date, 0),
        })
    context = _base_context(
        request,
        metrics={
            'users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'datasets': Dataset.objects.count(),
            'published': Dataset.objects.filter(status='published').count(),
            'attention': Dataset.objects.filter(attention_q).count(),
            'orders': Order.objects.count(),
            'paid': paid,
            'pipeline': PipelineRun.objects.filter(status__in=['queued', 'running']).count(),
        },
        recent_datasets=Dataset.objects.select_related('user').order_by('-created')[:7],
        recent_orders=Order.objects.select_related('buyer', 'listing__dataset_version__dataset').order_by('-created_at')[:7],
        quality_queue=Dataset.objects.select_related('user').filter(attention_q).order_by('-created')[:7],
        chart_data=daily,
        chart_max=max(max((point['datasets'] for point in daily), default=0), 1),
        order_max=max(max((point['orders'] for point in daily), default=0), 1),
        active_nav='overview',
    )
    return render(request, 'dashboard/overview.html', context)


@staff_required
def datasets(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    queryset = Dataset.objects.select_related('user').order_by('-created')
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(referenceOwner__icontains=query) | Q(user__username__icontains=query))
    if status:
        queryset = queryset.filter(status=status)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'dashboard/datasets.html', _base_context(request, page_obj=page_obj, query=query, selected_status=status, statuses=Dataset._meta.get_field('status').choices, active_nav='datasets'))


@staff_required
@require_POST
def dataset_status(request, dataset_id):
    dataset = get_object_or_404(Dataset, pk=dataset_id)
    status = request.POST.get('status', '').strip()
    valid = {value for value, _ in Dataset._meta.get_field('status').choices}
    if status not in valid:
        messages.error(request, 'Invalid dataset status.')
    else:
        latest = dataset.versions.order_by('-version').first()
        if status == 'published':
            report = QualityReport.objects.filter(dataset_version=latest).first() if latest else None
            if not latest or not report or report.result == QualityReport.Result.FAIL:
                messages.error(request, _text(request)[0]['publish_blocked'])
                return redirect(request.POST.get('next') or reverse('dashboard:datasets'))
        dataset.status = status
        dataset.save(update_fields=['status'])
        if latest and status in {choice for choice, _ in DatasetVersion._meta.get_field('status').choices}:
            latest.status = status
            if status == 'published':
                latest.published_at = timezone.now()
                latest.published_by = request.user
                latest.assets.update(status='published')
                latest.save(update_fields=['status', 'published_at', 'published_by'])
            else:
                latest.save(update_fields=['status'])
        messages.success(request, _text(request)[0]['status_saved'])
    return redirect(request.POST.get('next') or reverse('dashboard:datasets'))


@staff_required
def users(request):
    query = request.GET.get('q', '').strip()
    queryset = User.objects.order_by('-date_joined')
    if query:
        queryset = queryset.filter(Q(username__icontains=query) | Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    page_obj = Paginator(queryset, 25).get_page(request.GET.get('page'))
    return render(request, 'dashboard/users.html', _base_context(request, page_obj=page_obj, query=query, active_nav='users'))


@staff_required
@require_POST
def toggle_user_active(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        messages.success(request, _text(request)[0]['user_updated'])
    return redirect(request.POST.get('next') or reverse('dashboard:users'))


@staff_required
def orders(request):
    status = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    queryset = Order.objects.select_related('buyer', 'listing__dataset_version__dataset').order_by('-created_at')
    if status:
        queryset = queryset.filter(status=status)
    if query:
        queryset = queryset.filter(Q(buyer__username__icontains=query) | Q(listing__dataset_version__dataset__name__icontains=query) | Q(idempotency_key__icontains=query))
    page_obj = Paginator(queryset, 25).get_page(request.GET.get('page'))
    return render(request, 'dashboard/orders.html', _base_context(request, page_obj=page_obj, query=query, selected_status=status, statuses=Order.Status.choices, active_nav='orders'))


def _api_url(job_id=None):
    base = getattr(settings, 'DATAHUB_API_IMPORT_URL', 'http://api:8001/api/v1/import-jobs/').rstrip('/') + '/'
    return base if job_id is None else f'{base}{job_id}/'


def _normalize_provider_id(provider, value):
    """Accept either provider IDs or the common dataset page URL formats."""
    value = (value or '').strip().rstrip('/')
    parsed = urlparse(value)
    if parsed.netloc:
        parts = [part for part in parsed.path.split('/') if part]
        if len(parts) >= 3 and parts[0] == 'datasets':
            value = '/'.join(parts[1:3])
        else:
            value = ''
    elif value.startswith('datasets/'):
        value = value[len('datasets/'):]
    value = value.split('?', 1)[0].split('#', 1)[0].strip('/')
    if provider in ProviderImportRequest.Provider.values and re.fullmatch(r'[A-Za-z0-9._/-]{1,500}', value or ''):
        return value
    return ''


def _signed_request(method, url, payload=None):
    secret = getattr(settings, 'EXTERNAL_IMPORT_HMAC_SECRET', '')
    if not secret:
        raise RuntimeError('missing_hmac_secret')
    # The API signs the exact request body. GET status checks must sign an
    # empty body rather than an empty JSON object.
    body = (
        json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        if payload is not None else b''
    )
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode('utf-8'), timestamp.encode('ascii') + b'.' + body, hashlib.sha256).hexdigest()
    headers = {'X-DataHub-Timestamp': timestamp, 'X-DataHub-Signature': signature}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    return requests.request(method, url, data=body, headers=headers, timeout=getattr(settings, 'DATAHUB_API_TIMEOUT', 30))


@staff_required
def imports(request):
    labels, _ = _text(request)
    if request.method == 'POST':
        provider = request.POST.get('provider', '').strip().lower()
        provider_id = _normalize_provider_id(provider, request.POST.get('provider_dataset_id', ''))
        owner = get_object_or_404(User, pk=request.POST.get('owner_id')) if request.POST.get('owner_id') else request.user
        if provider not in ProviderImportRequest.Provider.values:
            messages.error(request, labels['invalid_provider'])
        elif not provider_id or '..' in provider_id:
            messages.error(request, labels['invalid_id'])
        else:
            request_key = f'gui-dashboard-{uuid.uuid4()}'
            payload = {
                'request_key': request_key,
                'provider': provider,
                'provider_dataset_id': provider_id,
                'owner_user_id': owner.pk,
                'metadata': {'requested_from': 'admin_dashboard', 'requested_by': request.user.username},
            }
            try:
                response = _signed_request('POST', _api_url(), payload)
                data = response.json()
                if response.status_code not in (200, 202):
                    raise RuntimeError(data.get('error') or f'HTTP {response.status_code}')
                ProviderImportRequest.objects.create(api_job_id=data.get('id'), request_key=request_key, provider=provider, provider_dataset_id=provider_id, owner=owner, requested_by=request.user, status=data.get('status', ProviderImportRequest.Status.QUEUED))
                messages.success(request, labels['import_started'])
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                messages.error(request, labels['api_unavailable'] if isinstance(exc, (requests.RequestException, RuntimeError)) else str(exc))
        return redirect('dashboard:imports')
    owner_id = request.GET.get('owner')
    requests_qs = ProviderImportRequest.objects.select_related('owner', 'requested_by').order_by('-created_at')
    if owner_id:
        requests_qs = requests_qs.filter(owner_id=owner_id)
    return render(request, 'dashboard/imports.html', _base_context(request, import_requests=requests_qs[:30], owners=User.objects.filter(is_active=True).order_by('username'), active_nav='imports'))


@staff_required
@require_GET
def import_status(request, request_id):
    job = get_object_or_404(ProviderImportRequest, pk=request_id)
    try:
        response = _signed_request('GET', _api_url(job.api_job_id))
        data = response.json()
        if response.status_code != 200:
            return JsonResponse({'error': data.get('error', 'status_unavailable')}, status=502)
        job.status = data.get('status', ProviderImportRequest.Status.UNKNOWN)
        job.error_code = data.get('error_code') or ''
        job.gui_dataset_id = data.get('gui_dataset_id')
        job.gui_dataset_version_id = data.get('gui_dataset_version_id')
        job.last_checked_at = timezone.now()
        job.save(update_fields=['status', 'error_code', 'gui_dataset_id', 'gui_dataset_version_id', 'last_checked_at', 'updated_at'])
        return JsonResponse({'status': job.status, 'error_code': job.error_code, 'gui_dataset_id': job.gui_dataset_id, 'dataset_url': reverse('dataset:dataset_detail', args=[job.gui_dataset_id]) if job.gui_dataset_id else ''})
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return JsonResponse({'error': str(exc)}, status=502)
