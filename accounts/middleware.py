from django.shortcuts import redirect
from django.urls import reverse

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if request.user.is_authenticated and request.user.must_change_password:
            allowed = {reverse("force_password_change"), reverse("logout")}
            if request.path not in allowed and not request.path.startswith("/static/"):
                return redirect("force_password_change")
        return self.get_response(request)
