from rest_framework import serializers
from .models import User, Vet, FarmerRequest, Meeting
from .services.guest import normalize_phone

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'role']

class RegisterSerializer(serializers.Serializer):
    """Serializer for user registration with role selection."""
    
    phone = serializers.CharField(required=True, max_length=15)
    fullName = serializers.CharField(required=True, max_length=150, source='full_name')
    password = serializers.CharField(required=True, min_length=6, write_only=True)
    role = serializers.ChoiceField(
        choices=[User.Role.VET, User.Role.FARMER],
        required=False,
        default=User.Role.FARMER
    )
    
    def validate_phone(self, value):
        """Validate phone is not already registered."""
        phone = str(value).strip()
        if User.objects.filter(username=phone).exists() or User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return phone
    
    def validate_fullName(self, value):
        """Validate full name is not empty."""
        if not value.strip():
            raise serializers.ValidationError("Full name is required.")
        return value.strip()
    
    def validate_role(self, value):
        """Normalize and validate role."""
        if value:
            normalized_role = str(value).strip().upper()
            if normalized_role not in [User.Role.VET, User.Role.FARMER]:
                raise serializers.ValidationError(
                    f"Invalid role. Must be one of: {', '.join([User.Role.VET, User.Role.FARMER])}"
                )
            return normalized_role
        return User.Role.FARMER
    
    def create(self, validated_data):
        """Create a new user with the specified role."""
        user = User.objects.create_user(
            username=validated_data['phone'],
            phone=validated_data['phone'],
            first_name=validated_data['full_name'],
            role=validated_data['role'],  # Explicitly set role from validated data
            password=validated_data['password'],
        )
        return user
    
    def to_representation(self, instance):
        """Return user details after registration."""
        return {
            'success': True,
            'message': 'Account created successfully.',
            'username': instance.username,
            'role': instance.role,
        }

class VetSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Vet
        fields = ['id', 'user', 'speciality', 'experience', 'status']

class FarmerRequestSerializer(serializers.ModelSerializer):
    farmer = UserSerializer(read_only=True)
    assigned_vet = VetSerializer(read_only=True)
    meeting_link = serializers.SerializerMethodField()
    link_expires_at = serializers.SerializerMethodField()
    is_link_expired = serializers.SerializerMethodField()

    class Meta:
        model = FarmerRequest
        fields = [
            'id', 'farmer', 'animal_type', 'breed', 'gender', 'age', 
            'health_problem', 'problem', 'description', 'cow_image', 
            'status', 'assigned_vet', 'meeting_link', 'link_expires_at', 
            'is_link_expired', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'farmer', 'status', 'assigned_vet', 'created_at', 'updated_at', 'meeting_link']
    
    def get_meeting_link(self, obj):
        """Get farmer's meeting link from related Meeting object."""
        if hasattr(obj, 'meeting') and obj.meeting:
            return obj.meeting.farmer_link
        return None
    
    def get_link_expires_at(self, obj):
        """Return the link expiry timestamp."""
        if obj.link_expiry:
            return obj.link_expiry.isoformat()
        return None
    
    def get_is_link_expired(self, obj):
        """Check if the link has expired."""
        return obj.is_link_expired()


class ConsultationRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new consultation requests with detailed animal info."""
    
    class Meta:
        model = FarmerRequest
        fields = [
            'animal_type', 'breed', 'gender', 'age', 'health_problem', 'cow_image'
        ]
    
    def validate_animal_type(self, value):
        """Validate animal type is one of the allowed choices."""
        if value and value not in dict(FarmerRequest.AnimalType.choices).keys():
            raise serializers.ValidationError("Invalid animal type.")
        return value
    
    def validate_gender(self, value):
        """Validate gender is one of the allowed choices."""
        if value and value not in dict(FarmerRequest.Gender.choices).keys():
            raise serializers.ValidationError("Invalid gender.")
        return value
    
    def validate_health_problem(self, value):
        """Validate health problem description is not empty."""
        if value and not value.strip():
            raise serializers.ValidationError("Health problem description is required.")
        return value.strip() if value else value
    
    def create(self, validated_data):
        """Create a new consultation request."""
        request = self.context.get('request')
        validated_data['farmer'] = request.user
        validated_data['source'] = FarmerRequest.Source.PORTAL
        return FarmerRequest.objects.create(**validated_data)

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

class VetResponseSerializer(serializers.Serializer):
    """Serializer for Vet to accept or decline a consultation request."""
    
    action = serializers.ChoiceField(choices=['accept', 'decline'], required=True)
    
    def validate_action(self, value):
        """Validate action is accept or decline."""
        if value not in ['accept', 'decline']:
            raise serializers.ValidationError("Action must be 'accept' or 'decline'.")
        return value