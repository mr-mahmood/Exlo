# user_measurements/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import MeasurementsError, APIError
from users.models import User
from .serializers import (
    UserMeasurementSerializer,
    MeasurementPhotosSerializer,
)
from .models import Measurements, MeasurementPhotos
from core.pagination import CustomPagination


class UserMeasurementsListView(APIView):
    serializer_class = UserMeasurementSerializer
    pagination_class = CustomPagination

    def get(self, request):
        user: User = request.user

        measurements = (
            Measurements.objects.filter(user=user)
            .prefetch_related("photos")
            .order_by("-created_at")
        )

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(measurements, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "measurements")

    def post(self, request):
        user: User = request.user

        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)
        serializer.save(user=user)

        return Response(
            {"measurement": serializer.data}, status=status.HTTP_201_CREATED
        )


class UserMeasurementDetailView(APIView):
    serializer_class = UserMeasurementSerializer

    def get(self, request, measurement_id):
        user: User = request.user

        try:
            measurement = Measurements.objects.prefetch_related("photos").get(
                id=measurement_id,
                user=user,
            )
        except Measurements.DoesNotExist:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        serializer = self.serializer_class(measurement, context={"request": request})
        return Response({"measurements": serializer.data}, status=status.HTTP_200_OK)

    def put(self, request, measurement_id):
        user: User = request.user

        try:
            measurement = Measurements.objects.get(id=measurement_id, user=user)
        except Measurements.DoesNotExist:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        serializer = self.serializer_class(
            measurement,
            data=request.data,
            context={"request": request},
            partial=True,
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"measurement": serializer.data}, status=status.HTTP_200_OK)

    def delete(self, request, measurement_id):
        user: User = request.user

        try:
            measurement = Measurements.objects.get(id=measurement_id, user=user)
        except Measurements.DoesNotExist:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        measurement.delete()
        return Response(status=status.HTTP_200_OK)


class MeasurementPhotosView(APIView):
    serializer_class = MeasurementPhotosSerializer
    pagination_class = CustomPagination

    def get(self, request, measurement_id):
        user: User = request.user

        photos = MeasurementPhotos.objects.filter(
            measurements__id=measurement_id,
            measurements__user=user,
        ).select_related("measurements__user")

        if not photos:
            raise APIError(MeasurementsError.NO_EXISTING_MEASUREMENTS_PHOTOS)

        serializer = self.serializer_class(
            photos,
            many=True,
            context={"request": request},
        )

        return Response({"photos": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request, measurement_id):
        user: User = request.user

        measurement = Measurements.objects.filter(
            id=measurement_id,
            user=user,
        )

        if not measurement:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        photo_type = serializer.validated_data["type"]  # type: ignore

        old_photo = MeasurementPhotos.objects.filter(
            measurements__id=measurement_id,
            type=photo_type,
        )
        if old_photo:
            raise APIError(MeasurementsError.MEASUREMENTS_PHOTO_TYPE_EXIST)

        photo = serializer.save(measurements_id=measurement_id)

        response_serializer = self.serializer_class(
            photo,
            context={"request": request},
        )

        return Response(
            {"photo": response_serializer.data},
            status=status.HTTP_201_CREATED,
        )


class MeasurementPhotoDetailView(APIView):
    serializer_class = MeasurementPhotosSerializer

    def get(self, request, measurement_id, photo_id):
        user: User = request.user

        try:
            photo = MeasurementPhotos.objects.select_related("measurements__user").get(
                id=photo_id,
                measurements__id=measurement_id,
                measurements__user=user,
            )
        except MeasurementPhotos.DoesNotExist:
            raise APIError(MeasurementsError.PHOTO_NOT_FOUND)

        serializer = self.serializer_class(
            photo,
            context={"request": request},
        )
        return Response(
            {"photo": serializer.data},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, measurement_id, photo_id):
        user: User = request.user

        try:
            photo = MeasurementPhotos.objects.select_related("measurements__user").get(
                id=photo_id,
                measurements__id=measurement_id,
                measurements__user=user,
            )
        except MeasurementPhotos.DoesNotExist:
            raise APIError(MeasurementsError.PHOTO_NOT_FOUND)

        # Delete the physical file
        if photo.photo:
            photo.photo.delete(save=False)

        # Delete the database record
        photo.delete()

        return Response(
            status=status.HTTP_200_OK,
        )
