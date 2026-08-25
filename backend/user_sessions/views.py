from django.forms import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from core.errors import SessionError, APIError
from users.models import User
from .serializers import UserSessionSerializer
from .models import Session
from django.core.exceptions import ValidationError


class UserSessionPIView(APIView):
    serializer_class = UserSessionSerializer

    def get(self, request):
        """Get current user's sessions"""

        user: User = request.user
        sessions = Session.objects.filter(user=user)
        if not sessions.exists():
            raise APIError(SessionError.NO_EXISTING_SESSION)

        serializer = self.serializer_class(
            sessions,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "sessions": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

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
