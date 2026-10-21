from django import template
register = template.Library()

@register.filter
def crc(value):
    try: return ("₡{:,.0f}".format(value)).replace(",", ".")
    except (TypeError, ValueError): return "₡0"
