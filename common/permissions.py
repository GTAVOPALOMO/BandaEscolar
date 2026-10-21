from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_committee:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped

def admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != "ADMIN":
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped
