from django.urls import path
from . import views

urlpatterns = [
    path("stream-frame/", views.stream_frame),
    path("alignment/", views.stream_frame),  # reuse for single-image upload
]