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
from core.cache import (
    GYM_PHOTOS,
    GYM_DETAIL,
    GYM_LIST,
    cache_key,
    get_cache,
    invalidate_cache,
)


class GymPhotosAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GymPhotoSerializer

    def get(self, request, gym_id):
        key = cache_key(GYM_PHOTOS, gym_id)

        def build():
            gym = Gym.objects.get_gym(gym_id)
            photos = gym.photos.all()
            serializer = self.serializer_class(
                photos,
                many=True,
                context={"request": request},
            )
            return {"gym_photos": serializer.data}

        data = get_cache(key, build)
        return Response(data, status=status.HTTP_200_OK)


class GymPhotoCreateAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def post(self, request, gym_id):
        gym = Gym.objects.get_gym(gym_id)

        files = request.FILES.getlist("photos")

        if not files:
            raise APIError(GymError.PHOTO_FILE_REQUIRED)

        with transaction.atomic():
            for file in files:
                data = {"photo": file}

                serializer = self.serializer_class(
                    data=data,
                    context={"request": request, "gym": gym},
                )

                if not serializer.is_valid():
                    raise APIError(GymError.PHOTO_UPLOAD_FAILED)

                serializer.save()

            invalidate_cache(GYM_PHOTOS, gym.id)
            invalidate_cache(GYM_DETAIL, gym.id)
            invalidate_cache(GYM_LIST)

        return Response(status=status.HTTP_201_CREATED)


class GymPhotoDeleteAPIView(APIView):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = GymPhotoSerializer

    def delete(self, request, gym_id, photo_id):
        gym = Gym.objects.get_gym(gym_id)

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

        invalidate_cache(GYM_PHOTOS, gym.id)
        invalidate_cache(GYM_DETAIL, gym.id)
        invalidate_cache(GYM_LIST)

        return Response(status=status.HTTP_200_OK)
