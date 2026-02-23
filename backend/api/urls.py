from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'cameras', views.CameraViewSet, basename='camera')
router.register(r'detections', views.DetectionViewSet, basename='detection')
router.register(r'alerts', views.AlertViewSet, basename='alert')
router.register(r'dashboard', views.DashboardViewSet, basename='dashboard')

urlpatterns = [
    path('', include(router.urls)),
]