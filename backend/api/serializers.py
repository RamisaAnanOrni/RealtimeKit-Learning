from rest_framework import serializers
from .models import User, Vet, FarmerRequest, Meeting
from .services.guest import normalize_phone

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'role']

class VetSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Vet
        fields = ['id', 'user', 'speciality', 'experience', 'status']

class FarmerRequestSerializer(serializers.ModelSerializer):
    farmer = UserSerializer(read_only=True)
    assigned_vet = VetSerializer(read_only=True)

    class Meta:
        model = FarmerRequest
        fields = ['id', 'farmer', 'problem', 'description', 'cow_image', 'status', 'assigned_vet', 'created_at']
        read_only_fields = ['id', 'farmer', 'status', 'assigned_vet', 'created_at']

class MeetingSerializer(serializers.ModelSerializer):
    vet = VetSerializer(read_only=True)
    farmer = UserSerializer(read_only=True)

    class Meta:
        model = Meeting
        fields = ['id', 'request', 'vet', 'farmer', 'cloudflare_meeting_id', 'farmer_link', 'vet_link', 'status', 'created_at']

class GuestRequestCreateSerializer(serializers.Serializer):
    """Validate the payload for a guest request submission."""

    phone = serializers.CharField(required=True)
    problem = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_phone(self, value):
        phone = normalize_phone(value)
        if not phone:
            raise serializers.ValidationError("A valid phone number is required.")
        if len(phone) < 7 or len(phone) > 15:
            raise serializers.ValidationError(
                "Phone number must contain between 7 and 15 digits."
            )
        return phone

    def validate_problem(self, value):
        if not value.strip():
            raise serializers.ValidationError("Problem description is required.")
        return value.strip()