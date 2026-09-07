import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


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


class Livestock(models.Model):
    class AnimalType(models.TextChoices):
        CATTLE = "CATTLE", "Cattle"
        POULTRY = "POULTRY", "Poultry"
        GOAT = "GOAT", "Goat"

    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="livestock")
    animal_type = models.CharField(max_length=20, choices=AnimalType.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["farmer", "animal_type"], name="unique_farmer_animal_type")]


class RewardAccount(models.Model):
    farmer = models.OneToOneField(User, on_delete=models.CASCADE, related_name="reward_account")
    points = models.PositiveIntegerField(default=0)


# Vet Profile Model
class Vet(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        OFFLINE = "OFFLINE", "Offline"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vet_profile")
    speciality = models.CharField(max_length=255, default="General Veterinary")
    experience = models.IntegerField(default=0)  # years
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username} ({self.status})"


# Farmer Request Model
class FarmerRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ASSIGNED = "ASSIGNED", "Assigned"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        MEETING_CREATED = "MEETING_CREATED", "Meeting Created"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        GUEST = "GUEST", "Guest"
        PORTAL = "PORTAL", "Portal"

    class AnimalType(models.TextChoices):
        DOG = "DOG", "Dog"
        CAT = "CAT", "Cat"
        COW = "COW", "Cow"
        GOAT = "GOAT", "Goat"
        BUFFALO = "BUFFALO", "Buffalo"
        SHEEP = "SHEEP", "Sheep"
        POULTRY = "POULTRY", "Poultry"
        OTHER = "OTHER", "Other"

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"

    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="farmer_requests")
    
    # Consultation Details
    animal_type = models.CharField(max_length=20, choices=AnimalType.choices, null=True, blank=True)
    breed = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, null=True, blank=True)
    age = models.CharField(max_length=50, null=True, blank=True)  # e.g., "2 Years", "6 Months"
    health_problem = models.TextField(null=True, blank=True)  # Main health issue description
    
    # Legacy fields for backwards compatibility
    problem = models.CharField(max_length=555, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    cow_image = models.ImageField(upload_to="cow_images/", null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PORTAL)
    assigned_vet = models.ForeignKey(Vet, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_requests")
    
    # Meeting Links for Farmer and Vet
    farmer_link = models.TextField(null=True, blank=True)  # Farmer's video meeting link
    vet_link = models.TextField(null=True, blank=True)  # Vet's video meeting link
    
    # Link expiry tracking
    link_expiry = models.DateTimeField(null=True, blank=True)  # When the farmer's link expires
    expires_at = models.DateTimeField(null=True, blank=True)  # When the entire consultation expires
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Request #{self.id} - {self.farmer.username} ({self.status})"
    
    def is_link_expired(self):
        """Check if the meeting link has expired."""
        if not self.link_expiry:
            return False
        from django.utils import timezone
        return timezone.now() > self.link_expiry


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


# ============================================================================
# SIGNALS TO AUTO-CREATE VET & REWARD PROFILES ON USER CREATION
# ============================================================================

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role_upper = str(instance.role).upper()
        
        # If created user is a VET, auto-create Vet profile
        if role_upper == User.Role.VET or role_upper == "VET":
            Vet.objects.get_or_create(
                user=instance,
                defaults={
                    "speciality": "General Veterinary",
                    "experience": 0,
                    "status": Vet.Status.AVAILABLE,
                }
            )
            
        # If created user is a FARMER, auto-create RewardAccount
        elif role_upper == User.Role.FARMER or role_upper == "FARMER":
            RewardAccount.objects.get_or_create(farmer=instance)


# ============================================================================
# DECOUPLING GUARD: MEETING <=> FARMER REQUEST
#
# A FarmerRequest must never linger in an active state while its Meeting has
# been completed (ENDED) or removed (deleted). These signals close the related
# request automatically so stale cards never surface on the Vet Dashboard.
# ============================================================================

# Statuses which are still "open" from the request's point of view. Once a
# request reaches a terminal state (COMPLETED/DECLINED/CANCELLED) it is left
# untouched, even if a signal fires again.
_REQUEST_OPEN_STATUSES = [
    FarmerRequest.Status.PENDING,
    FarmerRequest.Status.ASSIGNED,
    FarmerRequest.Status.ACCEPTED,
    FarmerRequest.Status.MEETING_CREATED,
    FarmerRequest.Status.IN_PROGRESS,
]


@receiver(post_save, sender=Meeting)
def close_request_on_meeting_end(sender, instance, **kwargs):
    """Mark the related FarmerRequest COMPLETED when its Meeting ends."""
    if instance.status != Meeting.Status.ENDED:
        return
    FarmerRequest.objects.filter(
        id=instance.request_id,
        status__in=_REQUEST_OPEN_STATUSES,
    ).update(status=FarmerRequest.Status.COMPLETED)


@receiver(post_delete, sender=Meeting)
def close_request_on_meeting_delete(sender, instance, **kwargs):
    """Close the related FarmerRequest if its Meeting is removed."""
    request_id = getattr(instance, 'request_id', None)
    if not request_id:
        return
    FarmerRequest.objects.filter(
        id=request_id,
        status__in=_REQUEST_OPEN_STATUSES,
    ).update(status=FarmerRequest.Status.COMPLETED)