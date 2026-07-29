import requests
import uuid
from django.conf import settings


class CloudflareRealtimeKit:
    def __init__(self):
        # Read directly from Django Settings
        self.account_id = str(getattr(settings, "CLOUDFLARE_ACCOUNT_ID", "")).strip()
        self.app_id = str(getattr(settings, "CLOUDFLARE_APP_ID", "")).strip()
        self.api_token = str(getattr(settings, "CLOUDFLARE_API_TOKEN", "")).strip()

        # Cloudflare Realtime Kit Base URL
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/realtime/kit/{self.app_id}"
        )

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def create_meeting(self, title="Veterinary Consultation"):
        """Create a real Cloudflare Meeting"""
        url = f"{self.base_url}/meetings"
        payload = {"title": title}

        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers(),
            timeout=10
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Cloudflare API Error ({response.status_code}): {response.text}")

        return response.json()

    def create_participant(
        self,
        meeting_id,
        name,
        preset_name="group_call_participant",
        custom_participant_id=None,
    ):
        """Create a real Cloudflare Participant Token"""
        url = f"{self.base_url}/meetings/{meeting_id}/participants"

        if not custom_participant_id:
            custom_participant_id = f"user_{uuid.uuid4().hex[:12]}"

        payload = {
            "name": name,
            "preset_name": preset_name,
            "custom_participant_id": custom_participant_id,
        }

        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers(),
            timeout=10
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Cloudflare API Error ({response.status_code}): {response.text}")

        return response.json()