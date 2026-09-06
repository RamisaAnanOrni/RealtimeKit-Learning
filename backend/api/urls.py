from django.urls import path
from .views import (
    health_check,
    create_meeting,
    CustomLoginView,
    FarmerSignupView,
    CreateFarmerRequestView,
    FarmerDashboardView,
    FarmerRequestsListView,
    VetAssignedRequestsView,
    VetDashboardView,
    VetAssignedMeetingsView,
    VetResponseView,
    MeetingDetailByUUIDView,
    guest_request_create,
    guest_request_status,
    CreateConsultationRequestView,
    ConsultationStatusView,
)

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('meeting/create/', create_meeting, name='create_meeting'),
    path('auth/login/', CustomLoginView.as_view(), name='api_login'),
    path('auth/signup/', FarmerSignupView.as_view(), name='api_signup'),
    path('auth/register/', FarmerSignupView.as_view(), name='api_register'),  # Alias for signup
    path('farmer/request/create/', CreateFarmerRequestView.as_view(), name='farmer_request_create'),
    path('farmer/request/list/', FarmerRequestsListView.as_view(), name='farmer_request_list'),
    path('farmer/dashboard/', FarmerDashboardView.as_view(), name='farmer_dashboard'),
    path('farmer/consultation/create/', CreateConsultationRequestView.as_view(), name='consultation_create'),
    path('farmer/consultation/<str:request_id>/status/', ConsultationStatusView.as_view(), name='consultation_status'),
    path('vet/dashboard/', VetDashboardView.as_view(), name='vet_dashboard'),
    path('vet/request/list/', VetAssignedRequestsView.as_view(), name='vet_request_list'),
    path('vet/meetings/', VetAssignedMeetingsView.as_view(), name='vet_meetings'),
    path('vet/requests/<str:request_id>/respond/', VetResponseView.as_view(), name='vet_respond'),
    path('internal/meeting/<uuid:meeting_uuid>/', MeetingDetailByUUIDView.as_view(), name='meeting_detail_uuid'),
    path('guest/request/', guest_request_create, name='guest_request_create'),
    path('guest/request/<str:request_id>/', guest_request_status, name='guest_request_status'),
]