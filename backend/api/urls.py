from django.urls import path
from .views import health_check, create_meeting, join_meeting

urlpatterns = [
    path("health/", health_check),
    path("create-meeting/", create_meeting),
    path("join-meeting/", join_meeting),
]