from rest_framework import serializers
from monitoring.models import Camera, Detection, Alert, CameraHealth


class CameraSerializer(serializers.ModelSerializer):
    """Serializer for Camera model"""
    detection_count = serializers.SerializerMethodField()
    last_detection_time = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            'id', 'name', 'location', 'camera_type', 'rtsp_url',
            'usb_device', 'status', 'is_active', 'fps',
            'resolution_width', 'resolution_height', 'created_at',
            'updated_at', 'last_checked', 'last_detection',
            'detection_count', 'last_detection_time', 'health_status'
        ]
        read_only_fields = ['created_at', 'updated_at', 'last_checked', 'last_detection']

    def get_detection_count(self, obj):
        return obj.detections.count()

    def get_last_detection_time(self, obj):
        last_detection = obj.detections.first()
        return last_detection.created_at if last_detection else None

    def get_health_status(self, obj):
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