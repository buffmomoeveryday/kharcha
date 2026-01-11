from django import template

register = template.Library()


@register.filter(name="replace_underscore")
def replace_underscore(value):
    """Replaces underscores with spaces and capitalizes words"""
    if isinstance(value, str):
        return value.replace("_", " ").title()
    return value


@register.filter(name="replace")
def replace(value, arg):
    """Replaces all occurrences of the first half of the argument
    with the second half.
    Usage: {{ value|replace:"old,new" }}
    """
    if "," not in arg:
        return value

    old, new = arg.split(",")
    return str(value).replace(old, new)
