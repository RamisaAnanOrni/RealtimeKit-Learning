import requests
from django.conf import settings


class CloudflareRealtimeKit:
    def __init__(self):
        # Cloudflare Credentials from settings.py or env
        self.account_id = getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
        self.app_id = getattr(settings, 'CLOUDFLARE_APP_ID', '')
        self.api_token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')

        # Base API Endpoint (Do not duplicate /client/v4/accounts)
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/realtime/kit/{self.app_id}"
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def create_meeting(self, title="Veterinary Consultation"):
        """Create a new Cloudflare Realtime Meeting"""
        url = f"{self.base_url}/meetings"
        payload = {
            "title": title
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_participant(self, meeting_id, name, preset_name="group_call_participant"):
        """Generate Participant Token for Farmer / Vet"""
        url = f"{self.base_url}/meetings/{meeting_id}/participants"
        payload = {
            "name": name,
            "preset_name": preset_name
        }
        
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()