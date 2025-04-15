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


@register.filter(name='filesizeformat')
def filesizeformat(value, precision=1):
    """
    Formats the value like a 'human-readable' file size.
    precision: number of decimal places (default: 1)
    """
    try:
        size = float(value)
    except (ValueError, TypeError):
        return "0 bytes"

    for unit in ['bytes', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0:
            if unit == 'bytes':
                return "%d %s" % (size, unit)
            else:
                return "%.*f %s" % (precision, size, unit)
        size /= 1024.0
    return "%.*f %s" % (precision, size, 'PB')