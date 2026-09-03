from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import authenticate
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt

from .models import FarmerRequest, Livestock, Meeting, RewardAccount, User, Vet
from .serializers import (
    FarmerRequestSerializer,
    MeetingSerializer,
    GuestRequestCreateSerializer,
    RegisterSerializer,
    ConsultationRequestCreateSerializer,
)
from .permissions import IsFarmer, IsVet, IsAdminUserRole
from .services.cloudflare import CloudflareRealtimeKit
from .services.guest import find_or_create_farmer_by_phone

@xframe_options_exempt
def farmer_join(request):
    return render(request, 'meeting_join.html')

@xframe_options_exempt
def vet_join(request):
    return render(request, 'meeting_join.html')
# -----------------
# 1. HEALTH CHECK 
# -----------------
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "Backend is working successfully!"
    })


# -------------------
# 2. CREATE MEETING 
# -------------------
@api_view(["POST"])
@permission_classes([AllowAny])
def create_meeting(request):
    try:
        cloudflare = CloudflareRealtimeKit()

        # STEP 1 - Create Cloudflare Meeting
        meeting = cloudflare.create_meeting()
        meeting_data = meeting.get("data", {})
        meeting_id = meeting_data.get("id", "mock_meeting_id")

        # Optional: Check if request_id is sent from frontend
        request_id = request.data.get('request_id')
        farmer_request = None
        farmer_user = None
        vet_profile = None

        if request_id:
            try:
                farmer_request = FarmerRequest.objects.get(id=request_id)
                farmer_user = farmer_request.farmer
                vet_profile = farmer_request.assigned_vet
            except FarmerRequest.DoesNotExist:
                pass

        farmer_name = farmer_user.username if farmer_user else "Farmer"
        vet_name = vet_profile.user.username if (vet_profile and vet_profile.user) else "Veterinarian"

        # STEP 2 - Create Farmer Participant Token
        farmer_participant = cloudflare.create_participant(
            meeting_id=meeting_id,
            name=farmer_name,
            preset_name="group_call_participant",
        )
        farmer_data = farmer_participant.get("data", {})
        farmer_token = farmer_data.get("token") or farmer_data.get("auth_token", "")

        # STEP 3 - Create Veterinarian Participant Token
        vet_participant = cloudflare.create_participant(
            meeting_id=meeting_id,
            name=vet_name,
            preset_name="group_call_host",
        )
        vet_data = vet_participant.get("data", {})
        vet_token = vet_data.get("token") or vet_data.get("auth_token", "")

        # STEP 4 - Build Join URLs
        frontend_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000')

        farmer_join_url = f"{frontend_url}/farmer?token={farmer_token}"
        vet_join_url = f"{frontend_url}/vet?token={vet_token}"

        # STEP 5 - Save inside PostgreSQL Database (Meeting Model)
        meeting_instance = None
        if farmer_request and vet_profile and farmer_user:
            meeting_instance = Meeting.objects.create(
                request=farmer_request,
                vet=vet_profile,
                farmer=farmer_user,
                cloudflare_meeting_id=meeting_id,
                farmer_link=farmer_join_url,
                vet_link=vet_join_url,
                status=Meeting.Status.CREATED
            )
            # Update FarmerRequest status
            farmer_request.status = FarmerRequest.Status.MEETING_CREATED
            farmer_request.save()

        # STEP 6 - Return Response
        return Response({
            "success": True,
            "db_meeting_id": str(meeting_instance.id) if meeting_instance else None,
            "meeting": {
                "id": meeting_id,
                "title": meeting_data.get("title", "Veterinary Consultation"),
                "status": meeting_data.get("status", "CREATED"),
            },
            "farmer": {
                "id": farmer_data.get("id") or farmer_data.get("custom_participant_id", "farmer_id"),
                "name": farmer_name,
                "token": farmer_token,
                "join_url": farmer_join_url,
            },
            "vet": {
                "id": vet_data.get("id") or vet_data.get("custom_participant_id", "vet_id"),
                "name": vet_name,
                "token": vet_token,
                "join_url": vet_join_url,
            },
        })

    except Exception as e:
        import traceback
        traceback.print_exc()  
        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

# -------------
# 3. AUTH API 
# ------------
class CustomLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(username=username, password=password)

        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'role': user.role,
                'username': user.username
            })
        return Response({'detail': 'Invalid Credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class FarmerSignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------
# 4. FARMER APIs 
# ----------------
class CreateFarmerRequestView(generics.CreateAPIView):
    serializer_class = FarmerRequestSerializer
    permission_classes = [IsAuthenticated, IsFarmer]

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)

class FarmerRequestsListView(generics.ListAPIView):
    serializer_class = FarmerRequestSerializer
    permission_classes = [IsAuthenticated, IsFarmer]

    def get_queryset(self):
        return FarmerRequest.objects.filter(farmer=self.request.user).order_by('-created_at')


class FarmerDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsFarmer]

    def get(self, request):
        livestock = {
            item.animal_type: item.count
            for item in Livestock.objects.filter(farmer=request.user)
        }
        requests = FarmerRequest.objects.filter(farmer=request.user).order_by('-created_at')
        logs = [
            {
                'id': f'R-{item.id:03d}',
                'animal_id': item.problem[:12],
                'treatment': item.problem,
                'date': item.created_at.strftime('%b %d, %Y'),
                'status': item.get_status_display(),
            }
            for item in requests[:10]
        ]
        return Response({
            'user': {
                'id': request.user.id,
                'name': request.user.get_full_name() or request.user.username,
                'phone': request.user.phone,
            },
            'livestock': {
                'cattle': livestock.get(Livestock.AnimalType.CATTLE, 0),
                'poultry': livestock.get(Livestock.AnimalType.POULTRY, 0),
                'goats': livestock.get(Livestock.AnimalType.GOAT, 0),
            },
            'appointments': requests.filter(status__in=[FarmerRequest.Status.ASSIGNED, FarmerRequest.Status.MEETING_CREATED, FarmerRequest.Status.IN_PROGRESS]).count(),
            'rewards': RewardAccount.objects.filter(farmer=request.user).values_list('points', flat=True).first() or 0,
            'logs': logs,
        })


# ----------------
# 5. VET APIs 
# ---------------
class VetAssignedRequestsView(generics.ListAPIView):
    serializer_class = FarmerRequestSerializer
    permission_classes = [IsAuthenticated, IsVet]

    def get_queryset(self):
        if hasattr(self.request.user, 'vet_profile'):
            return FarmerRequest.objects.filter(assigned_vet=self.request.user.vet_profile).order_by('-created_at')
        return FarmerRequest.objects.none()


class VetResponseView(APIView):
    """Vet accepts or declines a consultation request.
    
    POST /api/vet/requests/<id>/respond/
    Body: {"action": "accept" | "decline"}
    
    - accept: Updates status to ACCEPTED and returns vet_link
    - decline: Updates status to DECLINED
    """
    permission_classes = [IsAuthenticated, IsVet]
    
    def post(self, request, request_id):
        try:
            # Get the consultation request assigned to this vet
            vet_profile = request.user.vet_profile
            consultation = FarmerRequest.objects.select_related('meeting').get(
                id=request_id,
                assigned_vet=vet_profile
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found or not assigned to you.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        from .serializers import VetResponseSerializer
        serializer = VetResponseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        action = serializer.validated_data['action']
        
        if action == 'accept':
            consultation.status = FarmerRequest.Status.ACCEPTED
            consultation.save()
            
            # Return vet link for immediate access
            vet_link = consultation.vet_link
            if not vet_link and hasattr(consultation, 'meeting'):
                vet_link = consultation.meeting.vet_link
            
            return Response({
                'status': 'ACCEPTED',
                'message': 'Consultation accepted. Join the video call.',
                'vet_link': vet_link,
                'consultation_id': consultation.id,
            }, status=status.HTTP_200_OK)
        
        elif action == 'decline':
            consultation.status = FarmerRequest.Status.DECLINED
            consultation.save()
            
            return Response({
                'status': 'DECLINED',
                'message': 'Consultation request declined.',
                'consultation_id': consultation.id,
            }, status=status.HTTP_200_OK)


# ----------------------------------------
# FARMER CONSULTATION ENDPOINTS
# ----------------------------------------
class CreateConsultationRequestView(generics.CreateAPIView):
    """Create a new tele-health consultation request."""
    serializer_class = ConsultationRequestCreateSerializer
    permission_classes = [IsAuthenticated, IsFarmer]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return the full consultation request details
        consultation = serializer.save()
        response_serializer = FarmerRequestSerializer(consultation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user, source=FarmerRequest.Source.PORTAL)


class ConsultationStatusView(APIView):
    """Get consultation request status (for polling). 
    
    Returns consultation details including:
    - Status (PENDING, LINK_GENERATED, EXPIRED, COMPLETED)
    - Meeting link (when available)
    - Link expiry timestamp
    - Assigned vet information
    """
    permission_classes = [IsAuthenticated, IsFarmer]

    def get(self, request, request_id):
        try:
            consultation = FarmerRequest.objects.select_related(
                'assigned_vet__user'
            ).get(id=request_id, farmer=request.user)
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get meeting link if it exists
        meeting_link = None
        link_expiry = None
        try:
            meeting = consultation.meeting
            meeting_link = meeting.farmer_link
            link_expiry = consultation.link_expiry
        except Meeting.DoesNotExist:
            pass

        serializer = FarmerRequestSerializer(consultation)
        data = serializer.data

        # Add computed fields for frontend
        data['meeting_link'] = meeting_link
        data['link_expiry'] = link_expiry.isoformat() if link_expiry else None
        data['is_expired'] = consultation.is_link_expired()
        data['can_join'] = (
            meeting_link is not None and 
            not consultation.is_link_expired() and 
            consultation.status == FarmerRequest.Status.MEETING_CREATED
        )

        return Response(data)


# ------------------------------------
# 6. INTERNAL NEXT.JS ENDPOINT
# ------------------------------------
class MeetingDetailByUUIDView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, meeting_uuid):
        try:
            meeting = Meeting.objects.get(id=meeting_uuid)
            return Response({
                'meeting_id': meeting.cloudflare_meeting_id,
                'farmer_username': meeting.farmer.username,
                'vet_username': meeting.vet.user.username,
                'status': meeting.status
            })
        except Meeting.DoesNotExist:
            return Response({'detail': 'Meeting Not Found'}, status=status.HTTP_404_NOT_FOUND)


# -----------------
# 7. GUEST APIs
# ----------------
@api_view(["POST"])
@permission_classes([AllowAny])
def guest_request_create(request):
    """Public endpoint for a guest to open a consultation request by phone.

    Finds or creates the farmer, then creates a PENDING request. If the farmer
    already has an open (PENDING/ASSIGNED) request it is returned instead of
    creating a duplicate. Never calls Cloudflare and never creates a Meeting.
    """
    serializer = GuestRequestCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    farmer = find_or_create_farmer_by_phone(data["phone"])

    open_request = (
        FarmerRequest.objects.filter(
            farmer=farmer,
            status__in=[
                FarmerRequest.Status.PENDING,
                FarmerRequest.Status.ASSIGNED,
            ],
        )
        .order_by("-created_at")
        .first()
    )
    if open_request:
        return Response({
            "success": True,
            "request_id": open_request.id,
            "status": open_request.status,
            "message": "You already have an open request. Returning the existing one.",
        })

    farmer_request = FarmerRequest.objects.create(
        farmer=farmer,
        problem=data["problem"],
        description=data.get("description", ""),
        status=FarmerRequest.Status.PENDING,
        assigned_vet=None,
        source=FarmerRequest.Source.GUEST,
    )

    return Response({
        "success": True,
        "request_id": farmer_request.id,
        "status": farmer_request.status,
        "message": "Request submitted successfully. A veterinarian will be assigned shortly.",
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def guest_request_status(request, request_id):
    """Public endpoint that reports a guest request's current status.

    The farmer join link is surfaced only after the admin generated the
    Cloudflare meeting (i.e. a related Meeting with a farmer_link exists).
    """
    try:
        farmer_request = FarmerRequest.objects.select_related(
            "assigned_vet__user"
        ).get(id=request_id)
    except FarmerRequest.DoesNotExist:
        return Response(
            {"detail": "Request Not Found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        meeting = farmer_request.meeting
    except Meeting.DoesNotExist:
        meeting = None

    payload = {
        "request_id": farmer_request.id,
        "status": farmer_request.status,
        "problem": farmer_request.problem,
        "message": "",
    }

    vet_user = (
        farmer_request.assigned_vet.user
        if farmer_request.assigned_vet and farmer_request.assigned_vet.user
        else None
    )
    if vet_user:
        payload["assigned_vet_name"] = "Dr. {}".format(
            vet_user.get_full_name() or vet_user.username
        )

    if meeting and meeting.farmer_link:
        payload["status"] = FarmerRequest.Status.MEETING_CREATED
        payload["farmer_join_link"] = meeting.farmer_link
        payload["message"] = (
            "A veterinarian is ready. Join the consultation using the link."
        )
    elif farmer_request.status == FarmerRequest.Status.PENDING:
        payload["message"] = (
            "Your request is pending. A veterinarian will be assigned soon."
        )
    elif farmer_request.status == FarmerRequest.Status.ASSIGNED:
        payload["message"] = (
            "A veterinarian has been assigned. The meeting link will be "
            "available soon."
        )
    elif farmer_request.status == FarmerRequest.Status.MEETING_CREATED:
        payload["message"] = (
            "A veterinarian has been assigned. The meeting link will be "
            "available soon."
        )

    return Response(payload)