from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
import json


class Camera(models.Model):
    """Camera model for conveyor monitoring"""
    CAMERA_TYPES = [
        ('rtsp', 'RTSP IP Camera'),
        ('usb', 'USB Camera'),
        ('file', 'Video File'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
        ('error', 'Error'),
    ]

    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, help_text="Location description")
    camera_type = models.CharField(max_length=20, choices=CAMERA_TYPES, default='rtsp')
    rtsp_url = models.CharField(max_length=500, blank=True, help_text="RTSP URL for IP cameras")
    usb_device = models.CharField(max_length=100, blank=True, help_text="USB device path (e.g., /dev/video0)")
    video_file = models.FileField(upload_to='videos/', blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    is_active = models.BooleanField(default=True)

    # Camera settings
    fps = models.IntegerField(default=30, help_text="Frames per second")
    resolution_width = models.IntegerField(default=1920)
    resolution_height = models.IntegerField(default=1080)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_detection = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.location}"

    def get_rtsp_url(self):
        """Get RTSP URL with credentials if needed"""
        # You can implement credential injection here
        return self.rtsp_url

    def is_online(self):
        """Check if camera was online recently"""
        if not self.last_checked:
            return False
        return (timezone.now() - self.last_checked).seconds < 300  # 5 minutes


class Detection(models.Model):
    """Store detection results from YOLO"""
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='detections')

    # Detection data
    objects_detected = models.JSONField(default=list, help_text="List of detected objects with classes and confidence")
    detection_count = models.IntegerField(default=0)
    jam_detected = models.BooleanField(default=False)
    jam_confidence = models.FloatField(default=0.0)

    # Image data
    image = models.ImageField(upload_to='detections/', null=True, blank=True)
    thumbnail = models.ImageField(upload_to='thumbnails/', null=True, blank=True)

    # Metadata
    processing_time = models.FloatField(default=0.0, help_text="Processing time in seconds")
    confidence_threshold = models.FloatField(default=0.5)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['camera', '-created_at']),
            models.Index(fields=['jam_detected', '-created_at']),
        ]

    def __str__(self):
        return f"Detection on {self.camera.name} at {self.created_at}"

    def save(self, *args, **kwargs):
        self.detection_count = len(self.objects_detected)
        super().save(*args, **kwargs)

    def get_objects_by_class(self, class_name):
        """Get detections of specific class"""
        return [obj for obj in self.objects_detected if obj.get('class') == class_name]


class Alert(models.Model):
    """Alerts for jams and other events"""
    ALERT_TYPES = [
        ('jam', 'Jam Detected'),
        ('oversize', 'Oversize Object'),
        ('camera_offline', 'Camera Offline'),
        ('system', 'System Alert'),
        ('safety', 'Safety Violation'),
    ]

    SEVERITY_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('false_positive', 'False Positive'),
    ]

    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='warning')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, null=True, blank=True)
    detection = models.ForeignKey(Detection, on_delete=models.CASCADE, null=True, blank=True)

    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)

    # Resolution
    acknowledged_by = models.CharField(max_length=100, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.created_at}"

    def acknowledge(self, user):
        self.status = 'acknowledged'
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()

    def resolve(self, notes=''):
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save()


class CameraHealth(models.Model):
    """Track camera health and statistics"""
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='health_logs')

    # Health metrics
    is_online = models.BooleanField(default=False)
    fps_actual = models.FloatField(default=0.0)
    frame_width = models.IntegerField(default=0)
    frame_height = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    # Connection stats
    connection_attempts = models.IntegerField(default=0)
    successful_connections = models.IntegerField(default=0)
    last_successful = models.DateTimeField(null=True, blank=True)

    # Performance
    cpu_usage = models.FloatField(default=0.0)
    memory_usage = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'

    def __str__(self):
        return f"{self.camera.name} health at {self.created_at}"