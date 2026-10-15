# gym_photos/views.py

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from gym_auth.permissions import IsAdminOrGymOwner
from gym.models import Gym
from core.errors import APIError, GymError
from .models import GymPhotos
from .serializers import GymPhotoSerializer


class GymPhotosAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymPhotoSerializer

    def get(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id, active_only=True)

        photos = gym.photos.all()  # type: ignore

        serializer = self.serializer_class(
            photos,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "gym_photos": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class GymPhotoCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id, active_only=True)

        files = request.FILES.getlist("photos")

        if not files:
            raise APIError(GymError.PHOTO_FILE_REQUIRED)

        with transaction.atomic():
            for file in files:
                data = {"photo": file}
                serializer = self.serializer_class(
                    data=data,
                    context={
                        "request": request,
                        "gym": gym,
                    },
                )

                if not serializer.is_valid():
                    raise APIError(GymError.PHOTO_UPLOAD_FAILED)

                serializer.save()

        return Response(status=status.HTTP_201_CREATED)


class GymPhotoDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def delete(self, request, gym_id, photo_id):
        gym = Gym.objects.get_gym(gym_id, active_only=True)

        try:
            queryset = GymPhotos.objects.select_related("gym")
            if gym:
                queryset = queryset.filter(gym=gym)
            photo = queryset.get(id=photo_id)
        except GymPhotos.DoesNotExist:
            raise APIError(GymError.PHOTO_NOT_FOUND)

        if photo.photo:
            photo.photo.delete(save=False)

        photo.delete()

        return Response(status=status.HTTP_200_OK)