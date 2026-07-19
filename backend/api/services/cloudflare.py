import requests
import uuid

from django.conf import settings


class CloudflareRealtimeKit:

    def __init__(self):
        print("\n========== CLOUDFLARE SETTINGS ==========")
        print("BASE URL:", settings.CLOUDFLARE_BASE_URL)
        print("ACCOUNT:", settings.CLOUDFLARE_ACCOUNT_ID)
        print("APP:", settings.CLOUDFLARE_APP_ID)
        print("TOKEN:", settings.CLOUDFLARE_API_TOKEN[:15] + "...")
        print("=========================================\n")

        base_url = settings.CLOUDFLARE_BASE_URL.rstrip("/")
        if not base_url.endswith("/client/v4"):
            base_url = f"{base_url}/client/v4"

        self.base_url = (
            f"{base_url}"
            f"/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}"
            f"/realtime/kit/{settings.CLOUDFLARE_APP_ID}"
        )

        self.headers = {
            "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        }


    # Create Meeting
    

    def create_meeting(self):

        response = requests.post(
            f"{self.base_url}/meetings",
            headers=self.headers,
            json={"title": "Vet Consultation"}
        )

        if not response.ok:
            print("========== CLOUDFLARE ERROR ==========")
            print("Status Code:", response.status_code)
            print("Response:", response.text)
            response.raise_for_status()

        return response.json()
    
    # Create Participant
  

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