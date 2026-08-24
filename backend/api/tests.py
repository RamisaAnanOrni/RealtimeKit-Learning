from django.test import TestCase

from .models import FarmerRequest, Meeting, User, Vet
from .services.guest import find_or_create_farmer_by_phone, normalize_phone
from .services.url_shortener import shorten_url
from unittest.mock import patch, Mock
import requests


class NormalizePhoneTests(TestCase):
    def test_strips_whitespace_and_symbols(self):
        self.assertEqual(normalize_phone(" +88 0171-234 5678 "), "8801712345678")

    def test_drops_leading_plus(self):
        self.assertEqual(normalize_phone("+8801712345678"), "8801712345678")

    def test_empty_input(self):
        self.assertEqual(normalize_phone("  abc  "), "")


class FindOrCreateFarmerByPhoneTests(TestCase):
    def test_creates_guest_farmer(self):
        farmer = find_or_create_farmer_by_phone("  +88 0171-111-2222 ")
        self.assertEqual(farmer.phone, "8801711112222")
        self.assertEqual(farmer.role, User.Role.FARMER)
        self.assertEqual(farmer.username, "guest_8801711112222")

    def test_reuses_existing_farmer(self):
        existing = User.objects.create_user(
            username="farmer1", phone="8801711112222", role=User.Role.FARMER
        )
        farmer = find_or_create_farmer_by_phone("+880 1711 112222")
        self.assertEqual(farmer, existing)
        self.assertEqual(User.objects.filter(phone="8801711112222").count(), 1)

    def test_rejects_vet_phone(self):
        vet_user = User.objects.create_user(
            username="vet1", phone="8801711112222", role=User.Role.VET
        )
        Vet.objects.create(user=vet_user, speciality="General")
        with self.assertRaises(Exception) as ctx:
            find_or_create_farmer_by_phone("8801711112222")
        self.assertIn("Vet", str(ctx.exception.detail))

    def test_rejects_admin_phone(self):
        User.objects.create_user(
            username="admin1", phone="8801711112222", role=User.Role.ADMIN
        )
        with self.assertRaises(Exception) as ctx:
            find_or_create_farmer_by_phone("8801711112222")
        self.assertIn("Admin", str(ctx.exception.detail))


class GuestRequestCreateTests(TestCase):
    def setUp(self):
        self.payload = {
            "phone": "+880 1711-123456",
            "problem": "Cow has fever",
            "description": "Not eating for 2 days",
        }

    def test_creates_request_and_farmer(self):
        response = self.client.post("/api/guest/request/", self.payload, format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["status"], "PENDING")
        request_obj = FarmerRequest.objects.get(id=body["request_id"])
        self.assertEqual(request_obj.source, FarmerRequest.Source.GUEST)
        self.assertIsNone(request_obj.assigned_vet)
        self.assertEqual(request_obj.farmer.phone, "8801711123456")

    def test_empty_phone_is_400(self):
        response = self.client.post(
            "/api/guest/request/", {"phone": "   ", "problem": "Fever"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_problem_is_400(self):
        response = self.client.post(
            "/api/guest/request/", {"phone": "+880171123456", "problem": "  "}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_vet_phone_is_400(self):
        vet_user = User.objects.create_user(
            username="vet1", phone="8801711112222", role=User.Role.VET
        )
        Vet.objects.create(user=vet_user, speciality="General")
        response = self.client.post(
            "/api/guest/request/",
            {"phone": "+880 1711-112222", "problem": "Fever"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_open_request_returns_existing(self):
        first = self.client.post("/api/guest/request/", self.payload, format="json")
        second = self.client.post("/api/guest/request/", self.payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.json()["request_id"], second.json()["request_id"]
        )
        self.assertEqual(FarmerRequest.objects.count(), 1)

    def test_post_never_creates_meeting(self):
        self.client.post("/api/guest/request/", self.payload, format="json")
        self.assertEqual(Meeting.objects.count(), 0)


class GuestRequestStatusTests(TestCase):
    def setUp(self):
        farmer = User.objects.create_user(
            username="guest_880171123456", phone="880171123456", role=User.Role.FARMER
        )
        self.request_obj = FarmerRequest.objects.create(
            farmer=farmer,
            problem="Cow has fever",
            description="Not eating",
            status=FarmerRequest.Status.PENDING,
            source=FarmerRequest.Source.GUEST,
        )

    def test_unknown_request_is_404(self):
        response = self.client.get("/api/guest/request/99999/")
        self.assertEqual(response.status_code, 404)

    def test_pending_no_join_link(self):
        response = self.client.get(f"/api/guest/request/{self.request_obj.id}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertNotIn("farmer_join_link", body)

    def test_assigned_no_join_link(self):
        vet_user = User.objects.create_user(
            username="vet1", phone="880171112222", role=User.Role.VET
        )
        vet = Vet.objects.create(user=vet_user, speciality="General")
        self.request_obj.assigned_vet = vet
        self.request_obj.status = FarmerRequest.Status.ASSIGNED
        self.request_obj.save()

        response = self.client.get(f"/api/guest/request/{self.request_obj.id}/")
        body = response.json()
        self.assertEqual(body["status"], "ASSIGNED")
        self.assertEqual(body["assigned_vet_name"], "Dr. vet1")
        self.assertNotIn("farmer_join_link", body)

    def test_meeting_created_with_join_link(self):
        vet_user = User.objects.create_user(
            username="vet1", phone="880171112222", role=User.Role.VET
        )
        vet = Vet.objects.create(user=vet_user, speciality="General")
        self.request_obj.assigned_vet = vet
        self.request_obj.status = FarmerRequest.Status.MEETING_CREATED
        self.request_obj.save()
        Meeting.objects.create(
            request=self.request_obj,
            vet=vet,
            farmer=self.request_obj.farmer,
            cloudflare_meeting_id="cf-123",
            farmer_link="http://localhost:3000/farmer?token=abc",
            vet_link="http://localhost:3000/vet?token=xyz",
        )

        response = self.client.get(f"/api/guest/request/{self.request_obj.id}/")
        body = response.json()
        self.assertEqual(body["status"], "MEETING_CREATED")
        self.assertEqual(
            body["farmer_join_link"], "http://localhost:3000/farmer?token=abc"
        )
        self.assertNotIn("vet_link", body)


class URLShortenerUnitTests(TestCase):
    def test_bitly_success(self):
        long = "http://example.com/very/long/url?with=params"
        mock_resp = Mock()
        mock_resp.status_code = 200
        # simulate Bitly response structure
        mock_resp.json.return_value = {"link": "http://bit.ly/short123"}

        with patch("api.services.url_shortener.requests.post", return_value=mock_resp):
            with patch("django.conf.settings.BITLY_TOKEN", "fake-token"):
                short = shorten_url(long)
                self.assertEqual(short, "http://bit.ly/short123")

    def test_bitly_timeout_fallback(self):
        long = "http://example.com/very/long/url"
        with patch("api.services.url_shortener.requests.post", side_effect=requests.exceptions.Timeout):
            short = shorten_url(long)
            self.assertEqual(short, long)


class CreateMeetingIntegrationTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(
            username="farmer1", phone="880171123456", role=User.Role.FARMER
        )
        self.vet_user = User.objects.create_user(
            username="vet1", phone="880171112222", role=User.Role.VET
        )
        self.vet = Vet.objects.create(user=self.vet_user, speciality="General")
        self.req = FarmerRequest.objects.create(
            farmer=self.farmer,
            problem="Cow fever",
            status=FarmerRequest.Status.ASSIGNED,
            assigned_vet=self.vet,
            source=FarmerRequest.Source.GUEST,
        )

    @patch("api.views.CloudflareRealtimeKit")
    def test_create_meeting_stores_shortened_links(self, mock_cf_class):
        # Mock Cloudflare client behavior
        instance = mock_cf_class.return_value
        instance.create_meeting.return_value = {"data": {"id": "m-123", "title": "t", "status": "CREATED"}}
        farmer_part = {"data": {"id": "p-f", "token": "farmer-token"}}
        vet_part = {"data": {"id": "p-v", "token": "vet-token"}}
        instance.create_participant.side_effect = [farmer_part, vet_part]

        with patch("api.views.shorten_url", return_value="http://bit.ly/abc"):
            response = self.client.post("/api/meeting/create/", {"request_id": str(self.req.id)}, format="json")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body.get("success"))
            self.assertEqual(body["farmer"]["join_url"], "http://bit.ly/abc")

            meeting = Meeting.objects.get(request=self.req)
            self.assertEqual(meeting.farmer_link, "http://bit.ly/abc")

    @patch("api.views.CloudflareRealtimeKit")
    def test_create_meeting_shortener_failure_fallback(self, mock_cf_class):
        instance = mock_cf_class.return_value
        instance.create_meeting.return_value = {"data": {"id": "m-456", "title": "t", "status": "CREATED"}}
        farmer_part = {"data": {"id": "p-f", "token": "farmer-token-2"}}
        vet_part = {"data": {"id": "p-v", "token": "vet-token-2"}}
        instance.create_participant.side_effect = [farmer_part, vet_part]

        # Simulate shorten_url raising an error; view should fall back to long URL
        with patch("api.views.shorten_url", side_effect=Exception("boom")):
            response = self.client.post("/api/meeting/create/", {"request_id": str(self.req.id)}, format="json")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            # join_url should be present and be the long URL (not shortened)
            self.assertIn("/farmer?token=farmer-token-2", body["farmer"]["join_url"])

            meeting = Meeting.objects.get(request=self.req)
            self.assertIn("/farmer?token=farmer-token-2", meeting.farmer_link)
