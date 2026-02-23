from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import timedelta
import logging

from monitoring.models import Camera, Detection, Alert, CameraHealth
from .serializers import (
    CameraSerializer, DetectionSerializer, AlertSerializer,
    DetectionCreateSerializer, CameraHealthSerializer, DetectionSummarySerializer
)

logger = logging.getLogger(__name__)


class CameraViewSet(viewsets.ModelViewSet):
    """ViewSet for Camera model"""
    queryset = Camera.objects.all()
    serializer_class = CameraSerializer
    permission_classes = [AllowAny]  # Change to IsAuthenticatedOrReadOnly in production

    def get_queryset(self):
        queryset = Camera.objects.all()

        # Filter by status
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)

        # Filter by active
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Search by name or location
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(location__icontains=search)
            )

        return queryset

    @action(detail=True, methods=['get'])
    def detections(self, request, pk=None):
        """Get detections for a specific camera"""
        camera = self.get_object()
        days = int(request.query_params.get('days', 7))
        limit = int(request.query_params.get('limit', 100))

        cutoff_date = timezone.now() - timedelta(days=days)
        detections = camera.detections.filter(
            created_at__gte=cutoff_date
        )[:limit]

        serializer = DetectionSerializer(
            detections,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get statistics for a specific camera"""
        camera = self.get_object()
        days = int(request.query_params.get('days', 7))

        cutoff_date = timezone.now() - timedelta(days=days)
        detections = camera.detections.filter(created_at__gte=cutoff_date)

        stats = {
            'camera_id': camera.id,
            'camera_name': camera.name,
            'total_detections': detections.count(),
            'jams_detected': detections.filter(jam_detected=True).count(),
            'avg_processing_time': detections.aggregate(
                avg=Avg('processing_time')
            )['avg'] or 0,
            'detections_by_day': detections.extra(
                {'day': "date(created_at)"}
            ).values('day').annotate(count=Count('id')).order_by('day')
        }

        return Response(stats)

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle camera active status"""
        camera = self.get_object()
        camera.is_active = not camera.is_active
        camera.save()

        return Response({
            'status': 'success',
            'is_active': camera.is_active
        })

    @action(detail=True, methods=['get'])
    def health(self, request, pk=None):
        """Get camera health history"""
        camera = self.get_object()
        limit = int(request.query_params.get('limit', 50))

        health_logs = camera.health_logs.all()[:limit]
        serializer = CameraHealthSerializer(health_logs, many=True)

        return Response(serializer.data)


class DetectionViewSet(viewsets.ModelViewSet):
    """ViewSet for Detection model"""
    queryset = Detection.objects.all().select_related('camera')
    serializer_class = DetectionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Detection.objects.all().select_related('camera')

        # Filter by camera
        camera_id = self.request.query_params.get('camera', None)
        if camera_id:
            queryset = queryset.filter(camera_id=camera_id)

        # Filter by jam detection
        jam_only = self.request.query_params.get('jam_only', None)
        if jam_only and jam_only.lower() == 'true':
            queryset = queryset.filter(jam_detected=True)

        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # Limit results
        limit = self.request.query_params.get('limit', None)
        if limit:
            try:
                queryset = queryset[:int(limit)]
            except ValueError:
                pass

        return queryset

    @action(detail=False, methods=['post'])
    def create_detection(self, request):
        """Create a new detection (for YOLO service to call)"""
        serializer = DetectionCreateSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.validated_data

            # Create detection
            detection = Detection.objects.create(
                camera_id=data['camera_id'],
                objects_detected=data['objects_detected'],
                jam_detected=data['jam_detected'],
                jam_confidence=data['jam_confidence'],
                processing_time=data['processing_time'],
                image=data.get('image')
            )

            # Update camera's last_detection
            Camera.objects.filter(id=data['camera_id']).update(
                last_detection=timezone.now()
            )

            # Create alert if jam detected
            if data['jam_detected'] and data['jam_confidence'] > 0.7:
                Alert.objects.create(
                    alert_type='jam',
                    severity='critical',
                    camera_id=data['camera_id'],
                    detection=detection,
                    message=f"Jam detected on camera {detection.camera.name} with {data['jam_confidence']:.2%} confidence",
                    details={
                        'confidence': data['jam_confidence'],
                        'objects': data['objects_detected']
                    }
                )

            response_serializer = DetectionSerializer(
                detection,
                context={'request': request}
            )
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def recent_jams(self, request):
        """Get recent jam detections"""
        hours = int(request.query_params.get('hours', 24))
        cutoff_date = timezone.now() - timedelta(hours=hours)

        jams = Detection.objects.filter(
            jam_detected=True,
            created_at__gte=cutoff_date
        ).select_related('camera')[:50]

        serializer = self.get_serializer(jams, many=True)
        return Response(serializer.data)


class AlertViewSet(viewsets.ModelViewSet):
    """ViewSet for Alert model"""
    queryset = Alert.objects.all().select_related('camera', 'detection')
    serializer_class = AlertSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Alert.objects.all().select_related('camera', 'detection')

        # Filter by status
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)

        # Filter by type
        alert_type = self.request.query_params.get('type', None)
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)

        # Filter by camera
        camera_id = self.request.query_params.get('camera', None)
        if camera_id:
            queryset = queryset.filter(camera_id=camera_id)

        return queryset

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert"""
        alert = self.get_object()
        user = request.user.username if request.user.is_authenticated else 'system'

        alert.acknowledge(user)
        serializer = self.get_serializer(alert)

        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        notes = request.data.get('notes', '')

        alert.resolve(notes)
        serializer = self.get_serializer(alert)

        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active (new + acknowledged) alerts"""
        active_alerts = Alert.objects.filter(
            status__in=['new', 'acknowledged']
        ).select_related('camera', 'detection')[:100]

        serializer = self.get_serializer(active_alerts, many=True)
        return Response(serializer.data)


class DashboardViewSet(viewsets.ViewSet):
    """ViewSet for dashboard statistics"""
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get dashboard summary statistics"""
        days = int(request.query_params.get('days', 7))
        cutoff_date = timezone.now() - timedelta(days=days)

        # Basic stats
        total_cameras = Camera.objects.count()
        active_cameras = Camera.objects.filter(is_active=True).count()

        # Detection stats
        recent_detections = Detection.objects.filter(
            created_at__gte=cutoff_date
        )

        total_detections = recent_detections.count()
        total_jams = recent_detections.filter(jam_detected=True).count()

        # Alert stats
        active_alerts = Alert.objects.filter(
            status__in=['new', 'acknowledged']
        ).count()

        # Processing stats
        avg_processing = recent_detections.aggregate(
            avg=Avg('processing_time')
        )['avg'] or 0

        # Detection rate (detections per hour)
        hours = days * 24
        detection_rate = total_detections / hours if hours > 0 else 0

        data = {
            'total_cameras': total_cameras,
            'active_cameras': active_cameras,
            'total_detections': total_detections,
            'total_jams': total_jams,
            'active_alerts': active_alerts,
            'avg_processing_time': round(avg_processing, 3),
            'detection_rate': round(detection_rate, 2),
            'period_days': days,
        }

        serializer = DetectionSummarySerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def timeline(self, request):
        """Get detection timeline for charts"""
        days = int(request.query_params.get('days', 7))
        cutoff_date = timezone.now() - timedelta(days=days)

        # Group detections by day
        detections_by_day = Detection.objects.filter(
            created_at__gte=cutoff_date
        ).extra(
            {'day': "date(created_at)"}
        ).values('day').annotate(
            total=Count('id'),
            jams=Count('id', filter=Q(jam_detected=True))
        ).order_by('day')

        # Format for charts
        timeline = []
        for item in detections_by_day:
            timeline.append({
                'date': item['day'],
                'detections': item['total'],
                'jams': item['jams']
            })

        return Response(timeline)

    @action(detail=False, methods=['get'])
    def camera_stats(self, request):
        """Get statistics per camera"""
        cameras = Camera.objects.filter(is_active=True)
        stats = []

        for camera in cameras:
            detection_count = camera.detections.count()
            last_detection = camera.detections.first()

            stats.append({
                'camera_id': camera.id,
                'camera_name': camera.name,
                'location': camera.location,
                'status': camera.status,
                'total_detections': detection_count,
                'last_detection': last_detection.created_at if last_detection else None,
                'has_alerts': Alert.objects.filter(
                    camera=camera,
                    status__in=['new', 'acknowledged']
                ).exists()
            })

        return Response(stats)