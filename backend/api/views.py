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

from .models import FarmerRequest, Meeting, Vet
from .serializers import FarmerRequestSerializer, MeetingSerializer
from .permissions import IsFarmer, IsVet, IsAdminUserRole
from .services.cloudflare import CloudflareRealtimeKit

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