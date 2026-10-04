from datetime import date, datetime
import os

from django import template
from django.utils.timezone import is_aware, localtime
from django.utils.translation import get_language

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


_ARABIC_MONTHS = {
    1: 'يناير',
    2: 'فبراير',
    3: 'مارس',
    4: 'أبريل',
    5: 'مايو',
    6: 'يونيو',
    7: 'يوليو',
    8: 'أغسطس',
    9: 'سبتمبر',
    10: 'أكتوبر',
    11: 'نوفمبر',
    12: 'ديسمبر',
}
_ARABIC_DIGITS = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')


def _language_code(language=None):
    return (language or get_language() or 'fa').split('-')[0].lower()


def _gregorian_datetime(value):
    """Return a datetime in the active timezone for Gregorian formatting."""
    if isinstance(value, datetime):
        return localtime(value) if is_aware(value) else value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


@register.filter
def localized_date(value, language=None):
    """Format a date using the selected UI language and calendar.

    Persian uses the Solar Hijri calendar, while English and Arabic use the
    Gregorian calendar. Arabic output uses Arabic month names and numerals.
    """
    if not value:
        return ''

    language = _language_code(language)
    try:
        if language == 'fa':
            return JalaliDate(value, locale='fa').strftime('%Y/%m/%d')

        current = _gregorian_datetime(value)
        if current is None:
            return ''
        if language == 'ar':
            formatted = f'{current.day:02d} {_ARABIC_MONTHS[current.month]} {current.year}'
            return formatted.translate(_ARABIC_DIGITS)
        return f'{current.strftime("%b")} {current.day}, {current.year}'
    except (TypeError, ValueError, OverflowError):
        return ''


@register.filter
def to_jalali(value):
    return JalaliDate(value, locale="fa")

@register.filter
def to_jalali_s(value):
    # Keep the legacy filter name for existing templates while making its
    # output follow the selected language.
    return localized_date(value)
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


@register.filter
def basename(value):
    return os.path.basename(value)



@register.filter
def has_product_type(products, product_type):
    """Check if products queryset contains specific product type"""
    return products.filter(type=product_type).exists()
