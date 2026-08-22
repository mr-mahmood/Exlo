from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from users.serializers import UserSignupSerializer, UserProfileSerializer
from users.models import User
from typing import cast


class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = UserSignupSerializer

    def post(self, request):

        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = cast(User, serializer.save())

        return Response(
            {
                "user": self.serializer_class(
                    user,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class UserProfilePIView(APIView):
    serializer_class = UserProfileSerializer

    def get(self, request):
        """Get current user's profile"""
        user: User = request.user
        serializer = self.serializer_class(user, context={"request": request})
        return Response(
            {
                "user": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        """Update current user's profile"""
        user: User = request.user
        serializer = self.serializer_class(
            instance=user,
            data=request.data,
            context={"request": request},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        updated_user = serializer.save()

        return Response(
            {
                "user": self.serializer_class(
                    updated_user,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminUserPIView(APIView):
    pass


class CoachStudentPIView(APIView):
    pass


class GymMemberPIView(APIView):
    pass
