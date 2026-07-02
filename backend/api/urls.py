from django.urls import path

from .views import (
    health_check,
    create_meeting,
)

urlpatterns = [
    path(
        "health/",
        health_check,
        name="health-check",
    ),

    path(
        "create-meeting/",
        create_meeting,
        name="create-meeting",
    ),
]