# user_measurements/views.py

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import MeasurementsError, APIError
from users.models import User
from .serializers import UserMeasurementSerializer
from .models import Measurements
from core.pagination import CustomPagination


class UserMeasurementsListView(APIView):
    serializer_class = UserMeasurementSerializer
    pagination_class = CustomPagination

    def get(self, request):
        user: User = request.user
        measurements = Measurements.objects.filter(user=user)

        if not measurements.exists():
            raise APIError(MeasurementsError.NO_EXISTING_MEASUREMENTS)

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

    def get(self, request, pk):
        user: User = request.user

        try:
            measurement = Measurements.objects.get(id=pk, user=user)
        except Measurements.DoesNotExist:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        serializer = self.serializer_class(measurement, context={"request": request})
        return Response({"measurements": serializer.data}, status=status.HTTP_200_OK)

    def put(self, request, pk):
        user: User = request.user

        try:
            measurement = Measurements.objects.get(id=pk, user=user)
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

    def delete(self, request, pk):
        user: User = request.user

        try:
            measurement = Measurements.objects.get(id=pk, user=user)
        except Measurements.DoesNotExist:
            raise APIError(MeasurementsError.MEASUREMENT_NOT_FOUND)

        measurement.delete()
        return Response(status=status.HTTP_200_OK)
