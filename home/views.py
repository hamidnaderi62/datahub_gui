from django.shortcuts import render


def home(request):
    return render(request, 'home/home.html', context={})


def home_fa(request):
    return render(request, 'home/home_fa.html', context={})
