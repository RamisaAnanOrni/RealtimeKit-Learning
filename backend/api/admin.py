import traceback
import uuid

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import FarmerRequest, Meeting, User, Vet
from .services.cloudflare import CloudflareRealtimeKit


# -----------------------
# 1. Custom User Admin
# ------------------------
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('id', 'username', 'email', 'phone', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'phone')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('role', 'phone')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Extra Info', {'fields': ('role', 'phone')}),
    )


# -----------------
# 2. Vet Admin
# -----------------
@admin.register(Vet)
class VetAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_vet_name', 'speciality', 'experience', 'status')
    list_filter = ('status', 'speciality')
    search_fields = ('user__username', 'user__first_name', 'speciality')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def get_vet_name(self, obj):
        return f"Dr. {obj.user.get_full_name() or obj.user.username}"

    get_vet_name.short_description = 'Vet Name'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(role=User.Role.VET)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ------------------------------------
# 3. Farmer Request Admin
# ------------------------------------
@admin.register(FarmerRequest)
class FarmerRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'farmer',
        'problem',
        'status',
        'source',
        'assigned_vet',
        'show_cow_image',
        'created_at',
    )
    list_filter = ('status', 'source', 'created_at')
    search_fields = ('farmer__username', 'problem', 'description')
    readonly_fields = ('show_cow_image_large',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'farmer', 'assigned_vet__user'
        )

    def show_cow_image(self, obj):
        if obj.cow_image:
            return format_html(
                '<img src="{}" width="50" height="50" style="object-fit:cover;'
                ' border-radius:5px;" />',
                obj.cow_image.url,
            )
        return "No Image"

    show_cow_image.short_description = 'Cow Image'

    def show_cow_image_large(self, obj):
        if obj.cow_image:
            return format_html(
                '<img src="{}" width="300" style="border-radius:8px;" />',
                obj.cow_image.url,
            )
        return "No Image Uploaded"

    show_cow_image_large.short_description = 'Uploaded Cow Image'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_vet":
            kwargs["queryset"] = Vet.objects.filter(
                status=Vet.Status.AVAILABLE
            )
        elif db_field.name == "farmer":
            kwargs["queryset"] = User.objects.filter(role=User.Role.FARMER)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Auto-transition a request to call-ready when the vet link is set.

        The admin may paste the vet's video-call join link into vet_link; once
        it holds a value the request is joinable from the vet dashboard, so it
        is promoted out of PENDING/ASSIGNED.
        """
        super().save_model(request, obj, form, change)
        if obj.vet_link and obj.status in (
            FarmerRequest.Status.PENDING,
            FarmerRequest.Status.ASSIGNED,
        ):
            FarmerRequest.objects.filter(pk=obj.pk).update(
                status=FarmerRequest.Status.ACCEPTED
            )

    actions = ['generate_meeting_action', 'assign_vet_with_links']

    @admin.action(description="Generate Meeting & Video Call Links")
    def generate_meeting_action(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta
        
        for req in queryset:
            if not req.assigned_vet:
                self.message_user(
                    request,
                    f"No Vet assigned for Request #{req.id}! Please assign a"
                    " Vet first.",
                    messages.ERROR,
                )
                continue

            try:
                cf = CloudflareRealtimeKit()
                meeting_res = cf.create_meeting()
                m_id = meeting_res["data"]["id"]

                farmer_p = cf.create_participant(
                    m_id,
                    name=req.farmer.username,
                    preset_name="group_call_participant",
                )
                vet_p = cf.create_participant(
                    m_id,
                    name=req.assigned_vet.user.username,
                    preset_name="group_call_host",
                )

                frontend_url = getattr(
                    settings, 'FRONTEND_BASE_URL', 'http://localhost:3000'
                )
                f_link = (
                    f"{frontend_url}/farmer?token={farmer_p['data']['token']}"
                )
                v_link = f"{frontend_url}/vet?token={vet_p['data']['token']}"

                Meeting.objects.create(
                    request=req,
                    vet=req.assigned_vet,
                    farmer=req.farmer,
                    cloudflare_meeting_id=m_id,
                    farmer_link=f_link,
                    vet_link=v_link,
                    status=Meeting.Status.CREATED,
                )

                # Update FarmerRequest with links and expiration
                req.farmer_link = f_link
                req.vet_link = v_link
                req.status = FarmerRequest.Status.ASSIGNED
                req.link_expiry = timezone.now() + timedelta(minutes=10)
                req.expires_at = timezone.now() + timedelta(minutes=10)
                req.save()

                req.assigned_vet.status = Vet.Status.BUSY
                req.assigned_vet.save()

                self.message_user(
                    request,
                    f"Meeting generated successfully for Request #{req.id}!",
                    messages.SUCCESS,
                )

            except Exception as e:
                print("\n" + "=" * 50)
                print(
                    f"ERROR TRACEBACK IN FarmerRequestAdmin Action (Request"
                    f" #{req.id}):"
                )
                traceback.print_exc()
                print("=" * 50 + "\n")

                self.message_user(
                    request,
                    f"Error processing Request #{req.id}: {str(e)}",
                    messages.ERROR,
                )
    
    @admin.action(description="Assign Vet & Set Expiration (10 mins)")
    def assign_vet_with_links(self, request, queryset):
        """Admin action to assign vets with manual link input capability."""
        from django.utils import timezone
        from datetime import timedelta
        
        for req in queryset:
            if not req.assigned_vet:
                self.message_user(
                    request,
                    f"No Vet assigned for Request #{req.id}! Please assign a Vet first.",
                    messages.ERROR,
                )
                continue
            
            try:
                # Set status to ASSIGNED and set expiration
                req.status = FarmerRequest.Status.ASSIGNED
                req.expires_at = timezone.now() + timedelta(minutes=10)
                req.link_expiry = timezone.now() + timedelta(minutes=10)
                req.save()
                
                req.assigned_vet.status = Vet.Status.BUSY
                req.assigned_vet.save()
                
                self.message_user(
                    request,
                    f"Request #{req.id} assigned to {req.assigned_vet}. Links expire in 10 minutes.",
                    messages.SUCCESS,
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing Request #{req.id}: {str(e)}",
                    messages.ERROR,
                )


# -----------------------------------------------
# 4. Meeting Admin (With Detailed Traceback)
# -----------------------------------------------
@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'request',
        'vet',
        'farmer',
        'status',
        'created_at',
        'generate_meeting_button',
    )
    readonly_fields = (
        'cloudflare_meeting_id',
        'display_farmer_link',
        'display_vet_link',
        'generate_meeting_button_detail',
    )
    exclude = ('farmer_link', 'vet_link')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'farmer', 'vet__user', 'request'
        )

    # Table List View Button
    def generate_meeting_button(self, obj):
        opts = self.model._meta
        url = reverse(
            f'admin:{opts.app_label}_{opts.model_name}_generate_meeting',
            args=[str(obj.id)],
        )
        return format_html(
            '<a class="button" style="background-color: #28a745; color: white;'
            ' padding: 4px 10px; border-radius: 4px; font-weight: bold;'
            ' text-decoration: none;" href="{}">Generate Links</a>',
            url,
        )

    generate_meeting_button.short_description = "Action"

    # Detail View Button
    def generate_meeting_button_detail(self, obj):
        if obj.id:
            opts = self.model._meta
            url = reverse(
                f'admin:{opts.app_label}_{opts.model_name}_generate_meeting',
                args=[str(obj.id)],
            )
            return format_html(
                '<a class="button" style="background-color: #007bff; color:'
                ' white; padding: 8px 15px; border-radius: 4px; font-weight:'
                ' bold; text-decoration: none;" href="{}">⚡ Generate / Refresh'
                ' Cloudflare Links</a>',
                url,
            )
        return "Save meeting first to enable link generation."

    generate_meeting_button_detail.short_description = "Generate Links"

    # Farmer Link Renderer
    def display_farmer_link(self, obj):
        if obj.farmer_link:
            return format_html(
                '<textarea readonly style="width: 100%; height: 50px;'
                ' font-family: monospace; border:1px solid #ccc;'
                ' padding:5px;">{}</textarea><br/>'
                '<button type="button"'
                " onclick=\"navigator.clipboard.writeText('{}')\""
                ' style="margin-top:5px; padding:5px 12px; background:#417690;'
                ' color:white; border:none; border-radius:4px;'
                ' cursor:pointer;">Copy Farmer Link</button>',
                obj.farmer_link,
                obj.farmer_link,
            )
        return "No link generated yet. Click the 'Generate Links' button."

    display_farmer_link.short_description = "Farmer Join Link"

    # Vet Link Renderer
    def display_vet_link(self, obj):
        if obj.vet_link:
            return format_html(
                '<textarea readonly style="width: 100%; height: 50px;'
                ' font-family: monospace; border:1px solid #ccc;'
                ' padding:5px;">{}</textarea><br/>'
                '<button type="button"'
                " onclick=\"navigator.clipboard.writeText('{}')\""
                ' style="margin-top:5px; padding:5px 12px; background:#417690;'
                ' color:white; border:none; border-radius:4px;'
                ' cursor:pointer;">Copy Vet Link</button>',
                obj.vet_link,
                obj.vet_link,
            )
        return "No link generated yet. Click the 'Generate Links' button."

    display_vet_link.short_description = "Veterinarian Join Link"

    # Custom URL Route Pattern
    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                '<uuid:object_id>/generate-meeting/',
                self.admin_site.admin_view(self.process_generate_meeting),
                name=f'{opts.app_label}_{opts.model_name}_generate_meeting',
            ),
        ]
        return custom_urls + urls

    # Button Action Handler
    def process_generate_meeting(self, request, object_id):
        opts = self.model._meta

        # Ensure object_id is a valid UUID object
        try:
            if isinstance(object_id, str):
                val_uuid = uuid.UUID(object_id)
            else:
                val_uuid = object_id

            meeting_instance = Meeting.objects.get(id=val_uuid)
        except (Meeting.DoesNotExist, ValueError):
            self.message_user(
                request,
                f"Meeting with ID '{object_id}' does not exist in Database!"
                " Did you click 'Save' first?",
                messages.ERROR,
            )
            return redirect(
                f"admin:{opts.app_label}_{opts.model_name}_changelist"
            )

        # Cloudflare API Execution
        try:
            cf = CloudflareRealtimeKit()
            meeting_res = cf.create_meeting()

            if (
                not meeting_res
                or "data" not in meeting_res
                or "id" not in meeting_res["data"]
            ):
                raise Exception(
                    "Failed to create Cloudflare meeting response:"
                    f" {meeting_res}"
                )

            m_id = meeting_res["data"]["id"]

            # Safe Name Extraction
            farmer_name = "Farmer"
            if meeting_instance.farmer and meeting_instance.farmer.username:
                farmer_name = meeting_instance.farmer.username
            elif (
                meeting_instance.request and meeting_instance.request.farmer
            ):
                farmer_name = meeting_instance.request.farmer.username

            vet_name = "Veterinarian"
            if (
                meeting_instance.vet
                and meeting_instance.vet.user
                and meeting_instance.vet.user.username
            ):
                vet_name = meeting_instance.vet.user.username
            elif (
                meeting_instance.request
                and meeting_instance.request.assigned_vet
            ):
                vet_name = meeting_instance.request.assigned_vet.user.username

            farmer_p = cf.create_participant(
                m_id, name=farmer_name, preset_name="group_call_participant"
            )
            vet_p = cf.create_participant(
                m_id, name=vet_name, preset_name="group_call_host"
            )

            frontend_url = getattr(
                settings, 'FRONTEND_BASE_URL', 'http://localhost:3000'
            )
            f_link = f"{frontend_url}/farmer?token={farmer_p['data']['token']}"
            v_link = f"{frontend_url}/vet?token={vet_p['data']['token']}"

            meeting_instance.cloudflare_meeting_id = m_id
            meeting_instance.farmer_link = f_link
            meeting_instance.vet_link = v_link
            meeting_instance.status = Meeting.Status.CREATED
            meeting_instance.save()

            if meeting_instance.request:
                meeting_instance.request.status = (
                    FarmerRequest.Status.MEETING_CREATED
                )
                meeting_instance.request.save()

            self.message_user(
                request,
                "Cloudflare Meeting & Tokens generated successfully for"
                f" Meeting #{meeting_instance.id}!",
                messages.SUCCESS,
            )

        except Exception as e:
            print("\n" + "=" * 50)
            print("FULL TRACEBACK OF THE SAVING ERROR IN MeetingAdmin:")
            traceback.print_exc()
            print("=" * 50 + "\n")

            self.message_user(
                request, f"Error generating meeting: {str(e)}", messages.ERROR
            )

        return redirect(
            f"admin:{opts.app_label}_{opts.model_name}_change",
            meeting_instance.id,
        )