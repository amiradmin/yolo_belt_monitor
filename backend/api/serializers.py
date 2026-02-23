from rest_framework import serializers
from monitoring.models import Camera, Detection, Alert, CameraHealth


class CameraSerializer(serializers.ModelSerializer):
    """Serializer for Camera model with dynamic fields based on source type"""
    detection_count = serializers.SerializerMethodField()
    last_detection_time = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()

    # Dynamic fields that change based on source_type
    source_display = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()
    video_file_url = serializers.SerializerMethodField()
    video_details = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            'id', 'name', 'location', 'source_type', 'camera_type',
            'rtsp_url', 'usb_device', 'video_file', 'video_file_url',
            'status', 'is_active', 'fps', 'resolution_width', 'resolution_height',
            'created_at', 'updated_at', 'last_checked', 'last_detection',
            'detection_count', 'last_detection_time', 'health_status',
            'source_display', 'source_url', 'video_details'
        ]
        read_only_fields = ['created_at', 'updated_at', 'last_checked', 'last_detection', 'video_file_url']

    def get_detection_count(self, obj):
        """Get total detections for this camera/video"""
        return obj.detections.count()

    def get_last_detection_time(self, obj):
        """Get most recent detection time"""
        last_detection = obj.detections.first()
        return last_detection.created_at if last_detection else None

    def get_health_status(self, obj):
        """Get health status only for live cameras"""
        if obj.source_type == 'live':
            try:
                latest_health = obj.health_logs.latest('created_at')
                return {
                    'is_online': latest_health.is_online,
                    'fps': latest_health.fps_actual,
                    'last_check': latest_health.created_at,
                    'error': latest_health.error_message
                }
            except CameraHealth.DoesNotExist:
                return None
        return None  # No health status for video files

    def get_source_display(self, obj):
        """Get human-readable source description"""
        if obj.source_type == 'live':
            if obj.camera_type == 'rtsp':
                return f"RTSP Camera - {obj.rtsp_url or 'Not configured'}"
            elif obj.camera_type == 'usb':
                return f"USB Camera - {obj.usb_device or 'Not configured'}"
        else:
            if obj.video_file:
                return f"Video File - {os.path.basename(obj.video_file.name)}"
            return "Video File - No file uploaded"
        return "Unknown source"

    def get_source_url(self, obj):
        """Get the appropriate URL/device based on source type"""
        if obj.source_type == 'live':
            if obj.camera_type == 'rtsp':
                return obj.rtsp_url
            elif obj.camera_type == 'usb':
                return obj.usb_device
        return None

    def get_video_file_url(self, obj):
        """Get URL for video file if exists"""
        if obj.source_type == 'video_file' and obj.video_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
        return None

    def get_video_details(self, obj):
        """Get video file details if it's a video source"""
        if obj.source_type == 'video_file' and obj.video_file:
            import os
            from datetime import timedelta

            file_path = obj.video_file.path if hasattr(obj.video_file, 'path') else None

            # Try to get video metadata if available
            duration = getattr(obj, 'duration', None)
            file_size = None

            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                # Format file size
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if file_size < 1024.0:
                        file_size = f"{file_size:.1f} {unit}"
                        break
                    file_size /= 1024.0

            return {
                'filename': os.path.basename(obj.video_file.name),
                'file_size': file_size,
                'duration': str(timedelta(seconds=duration)) if duration else None,
                'uploaded_at': obj.updated_at,
                'status': obj.status if hasattr(obj, 'status') else 'active'
            }
        return None

    def to_representation(self, instance):
        """Customize the representation based on source type"""
        data = super().to_representation(instance)

        # Remove irrelevant fields based on source type
        if instance.source_type == 'live':
            # For live cameras, remove video-specific fields
            data.pop('video_file_url', None)
            data.pop('video_details', None)

            # Add camera-specific info
            data['connection_info'] = {
                'type': instance.camera_type,
                'url': instance.rtsp_url if instance.camera_type == 'rtsp' else instance.usb_device,
                'is_online': data['health_status']['is_online'] if data['health_status'] else False
            }
        else:
            # For video files, remove camera-specific fields
            data.pop('rtsp_url', None)
            data.pop('usb_device', None)
            data.pop('health_status', None)
            data.pop('camera_type', None)
            data.pop('fps', None)
            data.pop('resolution_width', None)
            data.pop('resolution_height', None)

            # Add video-specific info
            data['video_info'] = data.pop('video_details', {})

            # Rename source_display for clarity
            data['file_info'] = data.pop('source_display', '')

        return data


class DetectionSerializer(serializers.ModelSerializer):
    """Serializer for Detection model"""
    camera_name = serializers.CharField(source='camera.name', read_only=True)
    camera_location = serializers.CharField(source='camera.location', read_only=True)
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = [
            'id', 'camera', 'camera_name', 'camera_location',
            'objects_detected', 'detection_count', 'jam_detected',
            'jam_confidence', 'image', 'image_url', 'thumbnail',
            'thumbnail_url', 'processing_time', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None

    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
        return None


class AlertSerializer(serializers.ModelSerializer):
    """Serializer for Alert model"""
    camera_name = serializers.CharField(source='camera.name', read_only=True)
    detection_time = serializers.DateTimeField(source='detection.created_at', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'alert_type', 'severity', 'status',
            'camera', 'camera_name', 'detection', 'detection_time',
            'message', 'details', 'acknowledged_by', 'acknowledged_at',
            'resolved_at', 'resolution_notes', 'created_at'
        ]
        read_only_fields = ['created_at']


class DetectionCreateSerializer(serializers.Serializer):
    """Serializer for creating a new detection via API"""
    camera_id = serializers.IntegerField()
    objects_detected = serializers.ListField(child=serializers.DictField(), default=list)
    jam_detected = serializers.BooleanField(default=False)
    jam_confidence = serializers.FloatField(default=0.0)
    processing_time = serializers.FloatField(default=0.0)
    image = serializers.ImageField(required=False)

    def validate_camera_id(self, value):
        try:
            Camera.objects.get(id=value)
        except Camera.DoesNotExist:
            raise serializers.ValidationError("Camera does not exist")
        return value


class CameraHealthSerializer(serializers.ModelSerializer):
    """Serializer for CameraHealth model"""

    class Meta:
        model = CameraHealth
        fields = '__all__'
        read_only_fields = ['created_at']


class DetectionSummarySerializer(serializers.Serializer):
    """Serializer for detection statistics"""
    total_detections = serializers.IntegerField()
    total_jams = serializers.IntegerField()
    active_cameras = serializers.IntegerField()
    recent_alerts = serializers.IntegerField()
    detection_rate = serializers.FloatField()
    avg_processing_time = serializers.FloatField()