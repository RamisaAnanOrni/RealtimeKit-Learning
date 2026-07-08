import requests
import uuid

from django.conf import settings


class CloudflareRealtimeKit:

    def __init__(self):
        self.base_url = (
            f"{settings.CLOUDFLARE_BASE_URL}"
            f"/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}"
            f"/realtime/kit/{settings.CLOUDFLARE_APP_ID}"
        )

        self.headers = {
            "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        }

    # -----------------------------------------
    # Create Meeting
    # -----------------------------------------

        # -----------------------------------------
    # Create Meeting
    # -----------------------------------------

    def create_meeting(self):

        response = requests.post(
            f"{self.base_url}/meetings",
            headers=self.headers,
            json={}
        )

        if not response.ok:
            print("========== CLOUDFLARE ERROR ==========")
            print("Status Code:", response.status_code)
            print("Response:", response.text)
            response.raise_for_status()

        return response.json()

    # -----------------------------------------
    # Create Participant
    # -----------------------------------------

        # -----------------------------------------
    # Create Participant
    # -----------------------------------------

    def create_participant(
        self,
        meeting_id,
        name,
        preset_name,
    ):

        response = requests.post(
            f"{self.base_url}/meetings/{meeting_id}/participants",
            headers=self.headers,
            json={
                "name": name,
                "preset_name": preset_name,
                "custom_participant_id": str(uuid.uuid4())
            }
        )

        if not response.ok:
            print("========== CLOUDFLARE ERROR ==========")
            print("Status Code:", response.status_code)
            print("Response:", response.text)
            response.raise_for_status()

        return response.json()