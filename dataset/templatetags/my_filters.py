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
