import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


# Custom Manager to handle 'ADMIN' role on createsuperuser
class CustomUserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        # Automatically set role to ADMIN for superusers
        extra_fields.setdefault('role', User.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


# Custom User Model
class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        VET = "VET", "Vet"
        FARMER = "FARMER", "Farmer"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.FARMER)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.username} ({self.role})"


# Vet Profile Model
class Vet(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        OFFLINE = "OFFLINE", "Offline"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vet_profile")
    speciality = models.CharField(max_length=255)
    experience = models.IntegerField(default=0)  # years
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username} ({self.status})"


# Farmer Request Model
class FarmerRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ASSIGNED = "ASSIGNED", "Assigned"
        MEETING_CREATED = "MEETING_CREATED", "Meeting Created"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        GUEST = "GUEST", "Guest"
        PORTAL = "PORTAL", "Portal"

    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="farmer_requests")
    problem = models.CharField(max_length=555)
    description = models.TextField()
    cow_image = models.ImageField(upload_to="cow_images/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PORTAL)
    assigned_vet = models.ForeignKey(Vet, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_requests")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request #{self.id} - {self.farmer.username} ({self.status})"


# Meeting Model
class Meeting(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        STARTED = "STARTED", "Started"
        ENDED = "ENDED", "Ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(FarmerRequest, on_delete=models.CASCADE, related_name="meeting")
    vet = models.ForeignKey(Vet, on_delete=models.CASCADE)
    farmer = models.ForeignKey(User, on_delete=models.CASCADE)
    cloudflare_meeting_id = models.CharField(max_length=1255, blank=True, null=True)
    
    
    farmer_link = models.TextField(blank=True, null=True)
    vet_link = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Meeting #{self.id} - Vet: {self.vet.user.username}"