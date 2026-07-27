from rest_framework import serializers
from .models import User, Vet, FarmerRequest, Meeting

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