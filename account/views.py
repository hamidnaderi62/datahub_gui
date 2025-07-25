from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.decorators import login_required
from .models import User, Profile
from dataset.models import Dataset, Product, Comment, Request
from django.core.paginator import Paginator
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string


User = get_user_model()


def user_register_fa1(request):
    context = {'errors': []}
    if request.user.is_authenticated:
        return redirect('home:home_fa')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            context['errors'].append('کلمه های عبور یکسان نمی باشند')
            return render(request, 'account/register_fa.html', context)

        if User.objects.filter(username=username).exists():
            context['errors'].append('نام کاربری تکراری می باشد')
            return render(request, 'account/register_fa.html', context)

        if User.objects.filter(email=email).exists():
            context['errors'].append('این ایمیل قبلا ثبت شده است')
            return render(request, 'account/register_fa.html', context)

        # Create user but set is_active=False until email is verified
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            is_active=False
        )

        # Generate verification token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Create verification link
        verification_url = request.build_absolute_uri(
            f'/verify-email/{uid}/{token}/'
        )

        # Send verification email
        subject = 'تایید ایمیل'
        message = render_to_string('account/verify_email_fa.html', {
            'user': user,
            'verification_url': verification_url,
        })

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
            html_message=message
        )

        # Redirect to a page explaining that verification email has been sent
        return redirect('account:verification_sent_fa')

    return render(request, 'account/register_fa.html', context)


def verify_email_fa(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect('account:verification_success_fa')
    else:
        return redirect('account:verification_failed_fa')


def user_login_fa(request):
    context = {'errors': []}
    if request.user.is_authenticated:
        return redirect('home:home_fa')

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('home:home_fa')
            else:
                context['errors'].append('حساب کاربری شما فعال نیست. لطفا ایمیل خود را تایید کنید.')
        else:
            context['errors'].append('نام کاربری یا کلمه عبور اشتباه است')

    return render(request, 'account/login_fa.html', context)







def user_register_fa(request):
    context = {'errors': []}
    if request.user.is_authenticated:
        return redirect('home:home_fa')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            context['errors'].append('کلمه های عبور یکسان نمی باشند')
            return render(request, 'account/register_fa.html', context)

        if User.objects.filter(username=username):
            context['errors'].append('نام کاربری تکراری می باشد')
            return render(request, 'account/register_fa.html', context)

        user = User.objects.create(username=username, email=email, password=make_password(password1))
        login(request, user)
        return redirect('home:home_fa')
    return render(request, 'account/register_fa.html', context)


def user_login_fa1(request):
    if request.user.is_authenticated:
        return redirect('home:home_fa')
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home:home_fa')
    return render(request, 'account/login_fa.html', context={})


def user_logout_fa(request):
    logout(request)
    return redirect('home:home_fa')

@login_required
def profile_account_fa(request):
    context = {'errors': []}
    if request.method == 'POST':
        if 'btn_change_profile' in request.POST:
            print('btn_change_profile')
            name = request.POST.get('name')
            phone = request.POST.get('phone')
            address = request.POST.get('address')
            site = request.POST.get('site')
            bio = request.POST.get('bio')
            # profile_tags = request.POST.get('profile_tags')

            Profile.objects.update_or_create(
                user=request.user,  # Field to check for existing record
                defaults={  # Fields to update/create
                    'name': name,
                    'phone': phone,
                    'address': address,
                    'site': site,
                    'bio': bio,
                }
            )
            if request.FILES.get('image'):
                image = request.FILES.get('image')
                profile = request.user.profile
                profile.image = image
                profile.save()
            return render(request, 'account/profile_account_fa.html', context)

        elif 'btn_change_password' in request.POST:
            current_password = request.POST.get('currentPassword')
            new_password = request.POST.get('newPassword')
            confirm_password = request.POST.get('confirmPassword')
            if check_password(current_password, request.user.password):
                if new_password != confirm_password:
                    context['errors'].append('کلمه های عبور یکسان نمی باشند')
                    return render(request, 'account/profile_account_fa.html', context)
                request.user.set_password(new_password)
                request.user.save()
                logout(request)
                return redirect('account:login_fa')
    return render(request, 'account/profile_account_fa.html', context)


def profile_dataset_fa(request):
    page_number = 1
    if request.method == 'GET':
        page_number = request.GET.get('page')
    my_datasets = Dataset.objects.filter(user_id=request.user.id).all().order_by('-id')
    paginator = Paginator(my_datasets, 9)
    my_datasets = paginator.get_page(page_number)
    return render(request, 'account/profile_dataset_fa.html', context={'my_datasets': my_datasets})


def profile_product_fa(request):
    if request.method == 'POST':
        dataset_id = request.POST.get('product_dataset')
        product_title = request.POST.get('product_title')
        product_type = request.POST.get('product_type')
        product_link = request.POST.get('product_link')
        product_productDate = datetime.now()
        product_image = request.FILES.get('product_image')
        product_desc = request.POST.get('product_desc')

        dataset = Dataset.objects.get(id=dataset_id)
        Product.objects.create(dataset=dataset, title=product_title, type=product_type, link=product_link, desc=product_desc, image=product_image, productDate=product_productDate)

    all_datasets = Dataset.objects.all().values('id', 'name').order_by('name')
    print(all_datasets)
    my_products = Product.objects.select_related('dataset').filter(dataset__user_id=request.user.id).order_by('-id')

    return render(request, 'account/profile_product_fa.html', context={'my_products': my_products,'all_datasets': all_datasets})


def profile_marketplace_fa(request):
    if request.method == 'POST':
        if 'btn_in_request_accept' in request.POST:
            Request.objects.filter(id=request.POST.get('request_id')).update(responseType='Accept', responseDate=datetime.now())
        elif 'btn_in_request_reject' in request.POST:
            Request.objects.filter(id=request.POST.get('request_id')).update(responseType='Reject', responseDate=datetime.now())

    user_datasets = Dataset.objects.filter(user_id=request.user.id)
    in_requests = Request.objects.filter(
        dataset__in=user_datasets,
        responseType='Request'
    ).select_related('dataset')

    #in_requests = Request.objects.filter(user_id=request.user.id, responseType='Request').select_related('dataset').select_related('user')

    # out_requests = Request.objects.all().select_related('dataset').filter(user_id=request.user.id).select_related('user')
    out_requests = Request.objects.filter(user_id=request.user.id).select_related('dataset').select_related(
        'user')
    return render(request, 'account/profile_marketplace_fa.html', context={'in_requests': in_requests
        , 'out_requests': out_requests})


def custom_permission_denied(request, exception=None):
    return render(request, 'account/403_fa.html', status=403)


def custom_page_not_found(request, exception=None):
    return render(request, 'account/404_fa.html', status=404)


