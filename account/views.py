from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.decorators import login_required
from .models import User, Profile
from dataset.models import Dataset, Product, Comment, Request
from django.core.paginator import Paginator
from datetime import datetime


def user_login_fa(request):
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


@login_required
def profile_account_fa(request):
    context = {'errors': []}
    if request.method == 'POST':
        if 'btn_change_profile' in request.POST:
            name = request.POST.get('name')
            phone = request.POST.get('phone')
            address = request.POST.get('address')
            site = request.POST.get('site')
            bio = request.POST.get('bio')
            # profile_tags = request.POST.get('profile_tags')
            Profile.objects.filter(user=request.user).update(name=name, phone=phone, address=address, site=site,
                                                             bio=bio)
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
                print(current_password)
                request.user.set_password(new_password)
                request.user.save()
                return render(request, 'account/login_fa.html', context)
    return render(request, 'account/profile_account_fa.html', context)


def profile_dataset_fa(request):
    page_number = 1
    if request.method == 'GET':
        page_number = request.GET.get('page')
    my_datasets = Dataset.objects.filter(user_id=request.user.id).all().order_by('-id')
    paginator = Paginator(my_datasets, 9)
    my_datasets = paginator.get_page(page_number)

    # all_datasets = Dataset.objects.all().values_list('id', 'name').order_by('name')
    all_datasets = Dataset.objects.all().order_by('name')
    print(all_datasets)
    my_products = Product.objects.select_related('dataset').filter(dataset__user_id=request.user.id).order_by('-id')
    return render(request, 'account/profile_dataset_fa.html', context={'my_datasets': my_datasets, 'my_products': my_products,'all_datasets': all_datasets})


def profile_dataset_add_product_fa(request):
    if request.method == 'POST':
        dataset_id = request.POST.get('dataset_id')
        product_title = request.POST.get('product_title')
        product_type = request.POST.get('product_type')
        product_link = request.POST.get('product_link')
        # product_productDate = request.POST.get('product_productDate')
        product_image = request.FILES.get('product_image')

        dataset = Dataset.objects.get(id=dataset_id)
        Product.objects.create(dataset=dataset, title=product_title, type=product_type, link=product_link, image=product_image)
    return render(request, 'account/profile_dataset_fa.html', context)

def profile_marketplace_fa(request):
    if request.method == 'POST':
        if 'btn_in_request_accept' in request.POST:
            Request.objects.filter(id=request.POST.get('request_id')).update(responseType='Accept', responseDate=datetime.now())
        elif 'btn_in_request_reject' in request.POST:
            Request.objects.filter(id=request.POST.get('request_id')).update(responseType='Reject', responseDate=datetime.now())

    in_requests = Request.objects.filter(user_id=request.user.id, responseType='Request').select_related(
        'dataset').select_related('user')
    out_requests = Request.objects.all().select_related('dataset').filter(user_id=request.user.id).select_related(
        'user')
    return render(request, 'account/profile_marketplace_fa.html', context={'in_requests': in_requests
        , 'out_requests': out_requests})



