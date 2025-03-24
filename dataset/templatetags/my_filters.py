from django import template

register = template.Library()


@register.filter
def split_by(value, delimiter):
    """
    Splits the string `value` by the given `delimiter`.
    Usage: {{ my_string|split_by:',' }}
    """
    if not value or not delimiter:
        return []
    return value.split(delimiter)


from persiantools.jdatetime import JalaliDate
from django.utils.timezone import now
@register.filter
def to_jalali(value):
    return JalaliDate(value, locale="fa")

@register.filter
def to_jalali_s(value):
    return JalaliDate(value, locale="fa").strftime("%Y/%m/%d")
@register.filter
def to_jalali_c(value):
    return JalaliDate(value, locale="fa").strftime('%c')


@register.filter
def days_ago(value):
    days = (now().date() - value.date()).days
    return  (f'{days} روز قبل ')
