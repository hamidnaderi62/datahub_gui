from django.shortcuts import render
from django.contrib.auth.models import User
from dataset.models import Dataset, Request

def home(request):
    return render(request, 'home/home.html', context={})


def home_fa(request):
    dataset_count = Dataset.objects.all().count()
    user_count = User.objects.all().count()
    request_count = Request.objects.filter(responseType='Accept').count()
    template = 'home/home.html' if request.LANGUAGE_CODE == 'fa' else 'home/home_i18n.html'
    return render(request, template, context={'dataset_count': dataset_count, 'user_count': user_count, 'request_count': request_count})


