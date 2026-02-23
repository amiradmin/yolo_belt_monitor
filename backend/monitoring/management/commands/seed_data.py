from django.core.management.base import BaseCommand
from monitoring.models import Camera, Detection, Alert
from django.utils import timezone
from datetime import timedelta
import random


class Command(BaseCommand):
    help = 'Seed database with sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            Detection.objects.all().delete()
            Alert.objects.all().delete()
            Camera.objects.all().delete()

        self.stdout.write('Creating sample cameras...')

        # Create cameras
        cameras = []
        camera_data = [
            {'name': 'Main Conveyor', 'location': 'Building A - Line 1'},
            {'name': 'Secondary Belt', 'location': 'Building A - Line 2'},
            {'name': 'Transfer Point', 'location': 'Building B - Transfer'},
            {'name': 'Sorting Area', 'location': 'Building C - Sorting'},
        ]

        for data in camera_data:
            camera = Camera.objects.create(
                name=data['name'],
                location=data['location'],
                camera_type='rtsp',
                rtsp_url=f'rtsp://camera-{data["name"].lower().replace(" ", "-")}.local/stream',
                status='active',
                is_active=True
            )
            cameras.append(camera)
            self.stdout.write(f"  Created camera: {camera.name}")

        self.stdout.write('Creating sample detections...')

        # Create detections for last 7 days
        for camera in cameras:
            for days_ago in range(7):
                for hour in range(24):
                    # Create 0-5 detections per hour
                    for _ in range(random.randint(0, 5)):
                        timestamp = timezone.now() - timedelta(days=days_ago, hours=random.randint(0, 23))

                        # Random detection data
                        jam_detected = random.random() < 0.1  # 10% chance of jam
                        objects_count = random.randint(1, 10)

                        objects = []
                        for i in range(objects_count):
                            objects.append({
                                'class': random.choice(['box', 'pallet', 'person', 'jam', 'object']),
                                'confidence': random.uniform(0.7, 0.99),
                                'bbox': [random.randint(0, 100) for _ in range(4)]
                            })

                        detection = Detection.objects.create(
                            camera=camera,
                            objects_detected=objects,
                            jam_detected=jam_detected,
                            jam_confidence=random.uniform(0.8, 0.95) if jam_detected else 0,
                            processing_time=random.uniform(0.1, 0.5),
                            created_at=timestamp
                        )

                        # Create alert for jams
                        if jam_detected:
                            Alert.objects.create(
                                alert_type='jam',
                                severity=random.choice(['warning', 'critical']),
                                camera=camera,
                                detection=detection,
                                message=f"Jam detected on {camera.name}",
                                status=random.choice(['new', 'acknowledged', 'resolved'])
                            )

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded data: {Camera.objects.count()} cameras, {Detection.objects.count()} detections, {Alert.objects.count()} alerts'))