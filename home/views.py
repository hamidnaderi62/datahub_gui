from django.shortcuts import render
from django.contrib.auth.models import User
from dataset.models import Dataset, Request

def home(request):
    return render(request, 'home/home.html', context={})


def home_fa(request):
    dataset_count = Dataset.objects.all().count()
    user_count = User.objects.all().count()
    request_count = Request.objects.filter(responseType='Accept').count()
    return render(request, 'home/home_fa.html', context={'dataset_count': dataset_count, 'user_count': user_count, 'request_count': request_count})


