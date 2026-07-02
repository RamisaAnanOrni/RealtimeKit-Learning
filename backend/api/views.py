import uuid
import requests

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

BASE_URL = "https://api.realtime.cloudflare.com/v2"


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "Backend is working successfully!"
    })


# --------------------------------------------------
# Create Meeting
# --------------------------------------------------

@api_view(["POST"])
def create_meeting(request):

    headers = {
        "Authorization": settings.DYTE_AUTH_HEADER,
        "Content-Type": "application/json",
    }

    # ---------------------------------------------
    # STEP 1 - Create Meeting
    # ---------------------------------------------

    meeting_response = requests.post(
        f"{BASE_URL}/meetings",
        headers=headers,
        json={
            "title": "Vet Consultation"
        }
    )

    print("\n========== CREATE MEETING ==========")
    print(meeting_response.status_code)
    print(meeting_response.text)

    if meeting_response.status_code not in [200, 201]:
        return Response(
            meeting_response.json(),
            status=meeting_response.status_code,
        )

    meeting = meeting_response.json()
    meeting_id = meeting["data"]["id"]

    # ---------------------------------------------
    # STEP 2 - Create Farmer
    # ---------------------------------------------

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
    print(farmer_response.status_code)
    print(farmer_response.text)

    if farmer_response.status_code not in [200, 201]:
        return Response(
            farmer_response.json(),
            status=farmer_response.status_code,
        )

    farmer = farmer_response.json()

    # ---------------------------------------------
    # STEP 3 - Create Vet
    # ---------------------------------------------

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
    print(vet_response.status_code)
    print(vet_response.text)

    if vet_response.status_code not in [200, 201]:
        return Response(
            vet_response.json(),
            status=vet_response.status_code,
        )

    vet = vet_response.json()

    # ---------------------------------------------
    # STEP 4 - Build Join Links
    # ---------------------------------------------

    frontend_url = "https://vetcall.insurecow.com"
    

    farmer_join_url = (
        f"{frontend_url}/farmer"
        f"?token={farmer['data']['token']}"
    )

    vet_join_url = (
        f"{frontend_url}/vet"
        f"?token={vet['data']['token']}"
    )

    # ---------------------------------------------
    # STEP 5 - Return Response
    # ---------------------------------------------

    if vet_response.status_code not in [200, 201]:
        return Response({"success": False, "error": vet}, status=vet_response.status_code)

    return Response({
        "success": True,

        "meeting": {
            "id": meeting_id,
            "title": meeting["data"]["title"],
        },

        "farmer": {
            "id": farmer["data"]["id"],
            "name": farmer["data"]["name"],
            "join_url": farmer_join_url,
        },

        "vet": {
            "id": vet["data"]["id"],
            "name": vet["data"]["name"],
            "join_url": vet_join_url,
        },
    })