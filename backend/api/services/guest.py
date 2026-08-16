"""Guest Mode helpers for the veterinary consultation backend.

Guest Mode lets an anonymous user open a consultation request using only a
phone number. No OTP/SMS verification is performed in v1 and vet assignment
remains an admin-only action.
"""

from rest_framework.exceptions import ValidationError

from api.models import User


def normalize_phone(phone):
    """Return a canonical phone string.

    Rule: trim surrounding whitespace, drop a single leading ``+`` if present,
    then keep only digit characters. The output is the E.164-style digit
    sequence without the ``+`` prefix, e.g. ``+880 1712-345678`` becomes
    ``8801712345678``.
    """
    if phone is None:
        return ""
    return "".join(ch for ch in str(phone).strip() if ch.isdigit())


def _unique_guest_username(phone):
    """Build a unique username for a guest farmer (``guest_<phone>``)."""
    base = f"guest_{phone}"
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username


def find_or_create_farmer_by_phone(phone):
    """Find or create the Farmer User owning the given phone number.

    Raises ``rest_framework.exceptions.ValidationError`` (HTTP 400) when the
    phone is empty/invalid or belongs to a non-FARMER account.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        raise ValidationError({"detail": "A valid phone number is required."})

    try:
        user = User.objects.get(phone=normalized)
    except User.DoesNotExist:
        return User.objects.create_user(
            username=_unique_guest_username(normalized),
            phone=normalized,
            role=User.Role.FARMER,
            is_active=True,
        )

    if user.role != User.Role.FARMER:
        role_label = user.get_role_display()
        raise ValidationError({
            "detail": (
                f"This phone number is registered to a {role_label} account. "
                "Guest access is only available for farmer numbers."
            )
        })
    return user
