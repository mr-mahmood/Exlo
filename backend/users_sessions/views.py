from django.forms import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import SessionError, APIError
from users.models import User
from .serializers import UserSessionSerializer
from .models import Session
from django.core.exceptions import ValidationError
from core.pagination import CustomPagination


class UserSessionListAPIView(APIView):
    serializer_class = UserSessionSerializer
    pagination_class = CustomPagination

    def get(self, request):
        user: User = request.user

        sessions = Session.objects.filter(user=user)

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(sessions, request, view=self)

        serializer = self.serializer_class(
            result_page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data, "sessions")


class UserSessionDeleteAPIView(APIView):

    def delete(self, request):
        """Delete User requested session"""
        user: User = request.user
        session_id = request.data.get("session_id")

        try:
            session = Session.objects.get(user=user, session_id=session_id)
        except (Session.DoesNotExist, ValidationError):
            raise APIError(SessionError.SESSION_NOT_FOUND)

        session.delete()

        return Response(
            status=status.HTTP_200_OK,
        )
