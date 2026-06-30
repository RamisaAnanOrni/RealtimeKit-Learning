import uuid
import requests

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

BASE_URL = "https://api.realtime.cloudflare.com/v2"


# ---------------------------------------
# Health Check
# ---------------------------------------
@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "Backend is working successfully!"
    })


# ---------------------------------------
# Create Meeting
# ---------------------------------------
@api_view(["POST"])
def create_meeting(request):

    headers = {
        "Authorization": settings.DYTE_AUTH_HEADER,
        "Content-Type": "application/json"
    }

    # ==========================
    # Create Meeting
    # ==========================
    meeting_response = requests.post(
        f"{BASE_URL}/meetings",
        headers=headers,
        json={
            "title": "Vet Consultation"
        }
    )

    print("\n========== CREATE MEETING ==========")
    print("Status Code:", meeting_response.status_code)
    print("Response:", meeting_response.text)

    meeting = meeting_response.json()

    # Stop here if meeting creation failed
    if meeting_response.status_code not in [200, 201]:
        return Response({
            "success": False,
            "step": "create_meeting",
            "response": meeting
        })

    meeting_id = meeting["data"]["id"]

    # ==========================
    # Create Farmer Participant
    # ==========================
    farmer_response = requests.post(
        f"{BASE_URL}/meetings/{meeting_id}/participants",
        headers=headers,
        json={
            "name": "Farmer",
            "preset_name": "group_call_participant",
            "custom_participant_id": str(uuid.uuid4())
        }
    )

    print("\n========== CREATE FARMER ==========")
    print("Status Code:", farmer_response.status_code)
    print("Response:", farmer_response.text)

    farmer = farmer_response.json()

    # ==========================
    # Create Vet Participant
    # ==========================
    vet_response = requests.post(
        f"{BASE_URL}/meetings/{meeting_id}/participants",
        headers=headers,
        json={
            "name": "Veterinarian",
            "preset_name": "group_call_host",
            "custom_participant_id": str(uuid.uuid4())
        }
    )

    print("\n========== CREATE VET ==========")
    print("Status Code:", vet_response.status_code)
    print("Response:", vet_response.text)

    vet = vet_response.json()

    return Response({
        "meeting": meeting,
        "farmer": farmer,
        "vet": vet
    })