# core/pagination.py

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status


class CustomPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data, result_name):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                f"{result_name}": data,
            },
            status=status.HTTP_200_OK,
        )
