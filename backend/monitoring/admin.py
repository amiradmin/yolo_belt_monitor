from django.contrib import admin
from django.utils.html import format_html
from .models import Camera, Detection, Alert, CameraHealth


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'camera_type', 'status', 'is_active', 'last_checked', 'detection_count']
    list_filter = ['camera_type', 'status', 'is_active', 'created_at']
    search_fields = ['name', 'location', 'rtsp_url']
    readonly_fields = ['created_at', 'updated_at', 'last_checked', 'last_detection']

    def detection_count(self, obj):
        return obj.detections.count()

    detection_count.short_description = 'Detections'


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera', 'detection_count', 'jam_detected', 'processing_time', 'created_at']
    list_filter = ['jam_detected', 'created_at', 'camera']
    search_fields = ['camera__name', 'objects_detected']
    readonly_fields = ['created_at', 'image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 200px;"/>', obj.image.url)
        return "No image"

    image_preview.short_description = 'Preview'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['id', 'alert_type', 'severity', 'status', 'camera', 'created_at']
    list_filter = ['alert_type', 'severity', 'status', 'created_at']
    search_fields = ['message', 'camera__name']
    readonly_fields = ['created_at']
    actions = ['mark_as_acknowledged', 'mark_as_resolved']

    def mark_as_acknowledged(self, request, queryset):
        queryset.update(status='acknowledged', acknowledged_by='admin', acknowledged_at=timezone.now())

    mark_as_acknowledged.short_description = "Mark selected alerts as acknowledged"

    def mark_as_resolved(self, request, queryset):
        queryset.update(status='resolved', resolved_at=timezone.now())


@admin.register(CameraHealth)
class CameraHealthAdmin(admin.ModelAdmin):
    list_display = ['camera', 'is_online', 'fps_actual', 'created_at']
    list_filter = ['is_online', 'created_at']
    readonly_fields = ['created_at']