import logging
import uuid

from django.contrib.auth import authenticate
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

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


logger = logging.getLogger(__name__)


def _request_lookup_kwarg(request_id):
    """Map a URL request_id to a FarmerRequest lookup kwarg.

    FarmerRequest.id is a BigAutoField (integer), but the frontend may send the
    1:1 Meeting UUID string as the public request handle. Validate the value
    shape before querying so the ORM raises DoesNotExist (clean 404) instead of
    a ValueError (500) on type-mismatched lookups.
    """
    try:
        int(str(request_id).strip())
        return {"id": request_id}
    except (ValueError, TypeError):
        pass

    try:
        return {"meeting__id": uuid.UUID(str(request_id))}
    except (ValueError, TypeError, AttributeError):
        raise FarmerRequest.DoesNotExist


def _deny_unless_farmer(request):
    """Return a 403 Response unless the user is an authenticated FARMER.

    DRF's IsAuthenticated/IsFarmer permissions would surface a 401 or a
    generic message before the handler runs, so request-creation endpoints
    perform this single source-of-truth check in the handler to guarantee
    a clear 403 for unauthenticated AND non-farmer (e.g. VET) callers.
    """
    if not request.user.is_authenticated:
        return Response(
            {
                "detail": (
                    "Authentication required. Please sign in with a farmer"
                    " account to create a request."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if str(request.user.role).upper() != User.Role.FARMER:
        return Response(
            {
                "detail": (
                    "Only farmer accounts can create requests. Please sign in"
                    " with a farmer account."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


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
                farmer_request = FarmerRequest.objects.get(
                    **_request_lookup_kwarg(request_id)
                )
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
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        denied = _deny_unless_farmer(request)
        if denied is not None:
            return denied
        return super().create(request, *args, **kwargs)

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
        try:
            logs = [
                {
                    'id': f'R-{item.id:03d}',
                    'animal_id': (item.problem or item.health_problem or 'N/A')[:12],
                    'treatment': item.problem or item.health_problem or 'N/A',
                    'date': item.created_at.strftime('%b %d, %Y'),
                    'status': item.get_status_display(),
                }
                for item in requests[:10]
            ]
        except Exception:
            # Never let a malformed request/log row 500 the whole dashboard.
            logs = []
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
        """Return requests that are ready to act on (admin-activated).

        A request is only visible once an Admin has created an active Meeting
        for it (status becomes MEETING_CREATED after link generation, or
        ASSIGNED after assignment). Brand-new PORTAL submissions (PENDING,
        no Meeting yet) are therefore hidden from the Vet Dashboard.

        - status IN (MEETING_CREATED, ASSIGNED): actionable -> Accept/Decline.
        - status IN (ACCEPTED, IN_PROGRESS): kept visible so the accepted
          card keeps its "Join Video Call" button until the call is ended.
        - meeting__isnull=False and meeting still live (CREATED/STARTED):
          requests whose Meeting was removed or completed are excluded,
          along with COMPLETED / DECLINED / CANCELLED / EXPIRED rows.
        """
        if not hasattr(self.request.user, 'vet_profile'):
            return FarmerRequest.objects.none()

        vet_profile = self.request.user.vet_profile
        actionable_statuses = ['MEETING_CREATED', 'ASSIGNED', 'ACCEPTED', 'IN_PROGRESS']
        active_meeting_statuses = [Meeting.Status.CREATED, Meeting.Status.STARTED]
        return FarmerRequest.objects.filter(
            status__in=actionable_statuses,
            meeting__isnull=False,
            meeting__status__in=active_meeting_statuses,
        ).filter(
            Q(assigned_vet=vet_profile) | Q(meeting__vet=vet_profile)
        ).order_by('-created_at', '-id')


class VetDashboardView(APIView):
    """Return dashboard statistics for the logged-in Vet.

    GET /api/vet/dashboard/

    Response:
    - total_consultations: completed consultations count
    - pending_requests: PENDING/ASSIGNED/ACCEPTED count
    - today_consultations: meetings created today
    - weekly_consultations: records created in the last 7 days
    - pending_requests_list: serialized pending requests with join links
    """
    permission_classes = [IsAuthenticated, IsVet]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        try:
            vet_profile = request.user.vet_profile
        except Vet.DoesNotExist:
            return Response(
                {'detail': 'Vet profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        assigned_requests = FarmerRequest.objects.filter(
            assigned_vet=vet_profile
        ).select_related('farmer', 'meeting', 'assigned_vet__user').order_by('-created_at', '-id')

        # A request only counts as pending once an Admin has created an active
        # Meeting for it (MEETING_CREATED / ASSIGNED). Brand-new PENDING portal
        # submissions are hidden until then. ACCEPTED / IN_PROGRESS stay in the
        # pending list so an already-accepted call keeps its Join button.
        # Requests whose associated Meeting was removed or completed (ENDED),
        # and rows in finished states, are strictly excluded.
        actionable_statuses = ['MEETING_CREATED', 'ASSIGNED', 'ACCEPTED', 'IN_PROGRESS']
        active_meeting_statuses = [Meeting.Status.CREATED, Meeting.Status.STARTED]
        pending = FarmerRequest.objects.filter(
            status__in=actionable_statuses,
            meeting__isnull=False,
            meeting__status__in=active_meeting_statuses,
        ).filter(
            Q(assigned_vet=vet_profile) | Q(meeting__vet=vet_profile)
        ).select_related('farmer', 'meeting', 'assigned_vet__user').order_by('-created_at', '-id')
        completed = assigned_requests.filter(status=FarmerRequest.Status.COMPLETED)

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)

        today_meetings = Meeting.objects.filter(
            vet=vet_profile,
            created_at__gte=today_start,
        ).count()

        pending_serializer = FarmerRequestSerializer(pending[:20], many=True)

        data = {
            'total_consultations': completed.count(),
            'pending_requests': pending.count(),
            'today_consultations': today_meetings,
            'weekly_consultations': assigned_requests.filter(
                created_at__gte=week_start
            ).count(),
            'pending_requests_list': pending_serializer.data,
        }
        return Response(data, status=status.HTTP_200_OK)


class VetAssignedMeetingsView(generics.ListAPIView):
    """Return video meetings assigned to the logged-in Vet.

    GET /api/vet/meetings/

    Each item maps to the frontend's Meeting shape (vet_link, farmer_link,
    request details, farmer info, status, etc.).
    """
    serializer_class = MeetingSerializer
    permission_classes = [IsAuthenticated, IsVet]

    def get_queryset(self):
        try:
            vet_profile = self.request.user.vet_profile
        except Vet.DoesNotExist:
            return Meeting.objects.none()

        # Only expose meetings tied to an ACTIVE request, and only while the
        # meeting itself is still live. Brand-new PENDING requests (no meeting)
        # are hidden here by design. Completed, declined and cancelled
        # consultations are filtered out so they never linger as "incoming
        # request" cards on the Vet Dashboard.
        active_request_statuses = ['MEETING_CREATED', 'ASSIGNED', 'ACCEPTED', 'IN_PROGRESS']
        active_meeting_statuses = [Meeting.Status.CREATED, Meeting.Status.STARTED]
        return Meeting.objects.filter(
            vet=vet_profile,
            status__in=active_meeting_statuses,
            request__status__in=active_request_statuses,
        ).select_related('request', 'farmer', 'vet__user').order_by('-created_at', '-id')


class VetResponseView(APIView):
    """Vet accepts or declines a consultation request.
    
    POST /api/vet/requests/<id>/respond/
    Body: {"action": "accept" | "decline"}
    
    - accept: Updates status to ACCEPTED and returns vet_link
    - decline: Updates status to DECLINED

    Parser classes are explicit so JSON bodies (from the frontend) and
    multipart/form-data (from tooling/dashboards) both parse reliably.
    """
    permission_classes = [IsAuthenticated, IsVet]
    parser_classes = [JSONParser, MultiPartParser]
    
    def post(self, request, request_id):
        try:
            # Requests only reach the dashboard after an Admin generates a
            # Meeting (status MEETING_CREATED / ASSIGNED). A vet may act on a
            # request when it has an active Meeting for them, or when it is
            # directly assigned to them.
            vet_profile = request.user.vet_profile
            consultation = FarmerRequest.objects.select_related('meeting').get(
                Q(assigned_vet=vet_profile) | Q(meeting__vet=vet_profile),
                **_request_lookup_kwarg(request_id),
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found or not assigned to you.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        from .serializers import VetResponseSerializer
        serializer = VetResponseSerializer(data=request.data)
        if not serializer.is_valid():
            # Safely handle a missing/empty body instead of 415/500.
            if not request.data:
                return Response(
                    {
                        'detail': (
                            'A JSON body with an "action" field is required'
                            ' (accept or decline).'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        action = serializer.validated_data['action']
        
        if action == 'accept':
            consultation.status = FarmerRequest.Status.ACCEPTED
            consultation.assigned_vet = vet_profile  # Claim the request
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


class CompleteConsultationView(APIView):
    """Mark a video consultation as completed/ended.

    POST /api/vet/requests/<request_id>/complete/

    Transitions the FarmerRequest to COMPLETED and its 1:1 Meeting to ENDED,
    so both the Vet and Farmer dashboards stop showing the join button and
    instead render the consultation as finished.
    """
    permission_classes = [IsAuthenticated, IsVet]

    def post(self, request, request_id):
        try:
            vet_profile = request.user.vet_profile
        except Vet.DoesNotExist:
            return Response(
                {'detail': 'Vet profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            consultation = FarmerRequest.objects.select_related('meeting', 'assigned_vet').get(
                assigned_vet=vet_profile,
                **_request_lookup_kwarg(request_id),
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found or not assigned to you.'},
                status=status.HTTP_404_NOT_FOUND
            )

        _complete_consultation(consultation)

        return Response({
            'status': 'COMPLETED',
            'message': 'Consultation marked as completed.',
            'consultation_id': consultation.id,
        }, status=status.HTTP_200_OK)


class CompleteConsultationByParticipantView(APIView):
    """Mark a consultation completed from either side of the call.

    POST /api/consultations/<request_id>/complete/

    Authorization: the request's OWNER (farmer) or the ASSIGNED vet may
    complete it. Both the FarmerRequest and its 1:1 Meeting are transitioned
    to COMPLETED / ENDED so the request disappears from the Vet Dashboard's
    "Incoming Farmer Requests" and shows COMPLETED in the Farmer Care History.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            consultation = FarmerRequest.objects.select_related('meeting', 'assigned_vet').get(
                **_request_lookup_kwarg(request_id),
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        is_owner = consultation.farmer_id == request.user.id
        is_assigned_vet = (
            consultation.assigned_vet_id is not None
            and request.user.id == consultation.assigned_vet.user_id
        )
        if not (is_owner or is_assigned_vet):
            return Response(
                {'detail': 'You are not part of this consultation.'},
                status=status.HTTP_403_FORBIDDEN
            )

        _complete_consultation(consultation)

        return Response({
            'status': 'COMPLETED',
            'message': 'Consultation marked as completed.',
            'consultation_id': consultation.id,
        }, status=status.HTTP_200_OK)


class FarmerJoinMeetingView(APIView):
    """Farmer signals they have entered the video room.

    POST /api/consultations/<request_id>/join/

    Transition: MEETING_CREATED/ASSIGNED -> ACCEPTED, and the Meeting is
    marked STARTED. Once ACCEPTED/IN_PROGRESS the join button remains visible
    to BOTH the farmer and the vet, so a refresh or reconnect never loses the
    link. Re-joins on an already-accepted/in-progress consultation are
    idempotent (200, status unchanged).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            consultation = FarmerRequest.objects.select_related('meeting').get(
                **_request_lookup_kwarg(request_id),
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if consultation.farmer_id != request.user.id:
            return Response(
                {'detail': 'You are not part of this consultation.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if consultation.status in (
            FarmerRequest.Status.COMPLETED,
            FarmerRequest.Status.DECLINED,
            FarmerRequest.Status.CANCELLED,
        ):
            return Response(
                {'detail': 'This consultation has already ended.'},
                status=status.HTTP_409_CONFLICT
            )

        if consultation.status not in (
            FarmerRequest.Status.ASSIGNED,
            FarmerRequest.Status.MEETING_CREATED,
            FarmerRequest.Status.ACCEPTED,
            FarmerRequest.Status.IN_PROGRESS,
        ):
            return Response(
                {'detail': 'The meeting link is not available yet.'},
                status=status.HTTP_409_CONFLICT
            )

        consultation.status = FarmerRequest.Status.ACCEPTED
        consultation.save(update_fields=['status', 'updated_at'])

        if (
            hasattr(consultation, 'meeting')
            and consultation.meeting.status == Meeting.Status.CREATED
        ):
            consultation.meeting.status = Meeting.Status.STARTED
            consultation.meeting.save(update_fields=['status'])

        return Response({
            'status': consultation.status,
            'message': 'You have joined the video consultation.',
            'consultation_id': consultation.id,
        }, status=status.HTTP_200_OK)


def _complete_consultation(consultation):
    """Shared transition: mark a FarmerRequest + its Meeting COMPLETED/ENDED."""
    consultation.status = FarmerRequest.Status.COMPLETED
    consultation.save(update_fields=['status', 'updated_at'])

    if hasattr(consultation, 'meeting'):
        consultation.meeting.status = Meeting.Status.ENDED
        consultation.meeting.save(update_fields=['status'])

    # Free the vet up so new requests can be assigned.
    if consultation.assigned_vet and consultation.assigned_vet.status != Vet.Status.OFFLINE:
        consultation.assigned_vet.status = Vet.Status.AVAILABLE
        consultation.assigned_vet.save(update_fields=['status'])


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    """Log the user out.

    POST /api/auth/logout/

    Always returns a clean 200 OK. If a refresh token is supplied and the
    SimpleJWT token_blacklist app is installed, the refresh token is rotated
    out / blacklisted; otherwise we simply drop the client-side session. The
    server treats this as best-effort token invalidation.
    """
    refresh = request.data.get('refresh') if request.data else None
    if refresh:
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            # Blacklist is best-effort (app not installed / invalid token).
            pass

    return Response(
        {'detail': 'Successfully logged out.'},
        status=status.HTTP_200_OK
    )


# ----------------------------------------
# FARMER CONSULTATION ENDPOINTS
# ----------------------------------------
class CreateConsultationRequestView(generics.CreateAPIView):
    """Create a new tele-health consultation request."""
    serializer_class = ConsultationRequestCreateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        denied = _deny_unless_farmer(request)
        if denied is not None:
            return denied

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
            ).get(
                farmer=request.user,
                **_request_lookup_kwarg(request_id),
            )
        except FarmerRequest.DoesNotExist:
            return Response(
                {'detail': 'Consultation request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Farmer's join link must survive every non-terminal state: regardless
        # of whether the Vet has already accepted/joined or the Farmer has
        # rejoined, the link stays live while the Meeting itself is active. It
        # is only hidden once the request reaches a terminal status (COMPLETED
        # / DECLINED / CANCELLED) or the Meeting is ENDED.
        meeting_link = None
        link_expiry = None
        meeting_active = False
        try:
            meeting = consultation.meeting
            meeting_link = meeting.farmer_link
            link_expiry = consultation.link_expiry
            meeting_active = meeting.status != Meeting.Status.ENDED
        except Meeting.DoesNotExist:
            pass

        serializer = FarmerRequestSerializer(consultation)
        data = serializer.data

        terminal_statuses = [
            FarmerRequest.Status.COMPLETED,
            FarmerRequest.Status.DECLINED,
            FarmerRequest.Status.CANCELLED,
        ]
        data['meeting_link'] = meeting_link
        data['link_expiry'] = link_expiry.isoformat() if link_expiry else None
        data['is_expired'] = consultation.is_link_expired()
        # Join link available as long as the request is NOT terminal and the
        # meeting is still active with a generated Cloudflare link.
        data['can_join'] = (
            meeting_link is not None
            and not consultation.is_link_expired()
            and meeting_active
            and consultation.status not in terminal_statuses
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

    The handler is fully exception-guarded: every failure mode (validation,
    duplicate phone race, DB constraint) surfaces as a 4xx with an exact error
    message instead of an unhandled 500.
    """
    try:
        serializer = GuestRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Creates (or reuses) the guest farmer User. A non-farmer phone (e.g. a
        # registered vet/admin number) raises a 400 ValidationError here.
        farmer = _get_or_create_guest_farmer(data["phone"])

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

        # Fallback defaults for the optional fields: guests only ever submit
        # phone/problem/description, so provide safe values for everything else
        # instead of leaving the row half-populated.
        farmer_request = FarmerRequest.objects.create(
            farmer=farmer,
            problem=data["problem"],
            description=data.get("description", ""),
            animal_type=data.get("animal_type") or FarmerRequest.AnimalType.UNKNOWN,
            breed=data.get("breed") or "N/A",
            gender=data.get("gender") or "",
            age=data.get("age") or "",
            status=FarmerRequest.Status.PENDING,
            assigned_vet=None,
            source=FarmerRequest.Source.GUEST,
            updated_at=timezone.now(),  # Ensure updated_at is populated
        )

        return Response({
            "success": True,
            "request_id": farmer_request.id,
            "status": farmer_request.status,
            "message": "Request submitted successfully. A veterinarian will be assigned shortly.",
        })
    except ValidationError as exc:
        # Serializer failures (bad/oversized fields) plus the guest service's
        # "invalid phone" / "phone belongs to a vet" errors.
        return Response(
            exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except IntegrityError:
        # Lost a race against another request creating the same guest user
        # (phone/username uniqueness). Log it and reply 400; the client can
        # simply retry — the retry will fetch the now-existing farmer.
        logger.exception("Concurrent guest request creation for phone=%s", data["phone"])
        return Response(
            {"detail": "This request could not be processed right now. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        # Safety net: never surface an unhandled 500. Log the traceback for
        # ops, return a precise 400 with the underlying error to the caller.
        logger.exception("Guest request creation failed unexpectedly")
        return Response(
            {"detail": "Failed to submit request: {}".format(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _get_or_create_guest_farmer(phone):
    """Wrap the guest-user lookup so a create race returns the winner's row."""
    try:
        return find_or_create_farmer_by_phone(phone)
    except IntegrityError:
        # Another in-flight request created this user between our get() and
        # create(). Re-fetch and reuse it (role check still applies).
        user = User.objects.filter(phone=phone).first()
        if user is not None and user.role == User.Role.FARMER:
            return user
        raise


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
        ).get(**_request_lookup_kwarg(request_id))
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