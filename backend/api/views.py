from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .services.cloudflare import CloudflareRealtimeKit


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

    try:
        cloudflare = CloudflareRealtimeKit()

        # -----------------------------------------
        # STEP 1 - Create Meeting
        # -----------------------------------------

        meeting = cloudflare.create_meeting()

        meeting_data = meeting["data"]
        meeting_id = meeting_data["id"]

        # -----------------------------------------
        # STEP 2 - Create Farmer
        # -----------------------------------------

        farmer = cloudflare.create_participant(
            meeting_id=meeting_id,
            name="Farmer",
            preset_name="group_call_participant",
        )

        farmer_data = farmer["data"]

        # -----------------------------------------
        # STEP 3 - Create Veterinarian
        # -----------------------------------------

        vet = cloudflare.create_participant(
            meeting_id=meeting_id,
            name="Veterinarian",
            preset_name="group_call_host",
        )

        vet_data = vet["data"]

        # -----------------------------------------
        # STEP 4 - Build Join URLs
        # -----------------------------------------

        frontend_url = "http://localhost:3000"

        farmer_join_url = (
            f"{frontend_url}/farmer"
            f"?token={farmer_data['token']}"
        )

        vet_join_url = (
            f"{frontend_url}/vet"
            f"?token={vet_data['token']}"
        )

        # -----------------------------------------
        # STEP 5 - Return Response
        # -----------------------------------------

        return Response({
            "success": True,

            "meeting": {
                "id": meeting_data["id"],
                "title": meeting_data.get("title", ""),
                "status": meeting_data.get("status"),
            },

            "farmer": {
                "id": farmer_data["id"],
                "name": farmer_data["name"],
                "join_url": farmer_join_url,
            },

            "vet": {
                "id": vet_data["id"],
                "name": vet_data["name"],
                "join_url": vet_join_url,
            },
        })

    except Exception as e:

        return Response(
            {
                "success": False,
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )