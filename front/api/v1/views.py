from collections.abc import Mapping

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from front.api.v1.serializers import (
    FrontDocxRequestSerializer,
    FrontMarkRequestSerializer,
)
from front.data_utils import resolve_front_result
from front.exceptions import (
    FrontDocxError,
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)
from front.utils import front_from_docx_upload


class FrontViewSet(GenericViewSet):
    serializer_class = FrontMarkRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if getattr(self, "action", None) == "docx":
            return FrontDocxRequestSerializer
        return FrontMarkRequestSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, Mapping):
            return JsonResponse({"error": "Error processing"}, status=400)

        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            return JsonResponse(serializer.errors, status=400)

        return self.mark_and_respond(
            serializer.validated_data["front"],
            serializer.validated_data.get("type", "json"),
            serializer.validated_data.get("language") or None,
        )

    @action(
        detail=False,
        methods=["get", "post"],
        url_path="docx",
        parser_classes=[MultiPartParser, FormParser],
    )
    def docx(self, request):
        if request.method == "GET":
            return Response({})

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse(serializer.errors, status=400)

        uploaded = serializer.validated_data["file"]
        output_type = serializer.validated_data.get("type", "json")
        language = serializer.validated_data.get("language") or None
        try:
            front_text = front_from_docx_upload(uploaded)
        except FrontDocxError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return self.mark_and_respond(front_text, output_type, language)

    def mark_and_respond(self, front_text, output_type, language):
        if not str(front_text or "").strip():
            return JsonResponse({"error": "No front provided"}, status=400)
        try:
            result = resolve_front_result(
                front_text,
                user=self.request.user,
                output_type=output_type,
                language=language,
            )
        except (
            FrontLlamaDisabledError,
            FrontLlamaMisconfiguredError,
            FrontLlamaUnavailableError,
        ) as exc:
            return JsonResponse(
                {"error": f"Llama model is not available: {exc}"},
                status=503,
            )
        return JsonResponse(result)
