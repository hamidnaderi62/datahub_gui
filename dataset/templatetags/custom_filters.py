from django import template
import os
from urllib.parse import unquote

register = template.Library()


@register.filter
def basename(value):
    """Extract base filename from object_key or URL"""
    if not value:
        return "Unknown"
    try:
        # If it's a full URL, extract the object key part first
        if 'teh-1.s3.poshtiban.com' in value:
            path = value.split('teh-1.s3.poshtiban.com/')[-1]
            # Remove bucket name to get just object key
            parts = path.split('/', 1)
            if len(parts) > 1:
                object_key = parts[1]
            else:
                object_key = path
        else:
            object_key = value

        # Get just the filename
        filename = os.path.basename(unquote(object_key))
        return filename or "Unknown File"
    except:
        return "Unknown File"


@register.filter
def get_file_extension(value):
    """Get file extension from object_key"""
    if not value:
        return ""
    try:
        filename = basename(value)
        if '.' in filename:
            return filename.split('.')[-1].lower()
        return ""
    except:
        return ""