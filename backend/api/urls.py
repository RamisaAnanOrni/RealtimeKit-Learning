from django.urls import path
from .views import (
    health_check,
    create_meeting,
    CustomLoginView,
    CreateFarmerRequestView,
    FarmerRequestsListView,
    VetAssignedRequestsView,
    MeetingDetailByUUIDView
)

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('meeting/create/', create_meeting, name='create_meeting'),
    path('auth/login/', CustomLoginView.as_view(), name='api_login'),
    path('farmer/request/create/', CreateFarmerRequestView.as_view(), name='farmer_request_create'),
    path('farmer/request/list/', FarmerRequestsListView.as_view(), name='farmer_request_list'),
    path('vet/request/list/', VetAssignedRequestsView.as_view(), name='vet_request_list'),
    path('internal/meeting/<uuid:meeting_uuid>/', MeetingDetailByUUIDView.as_view(), name='meeting_detail_uuid'),
]