from collections.abc import Mapping

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from body.api.v1.serializers import BodyDocxRequestSerializer, BodyMarkRequestSerializer
from body.data_utils import resolve_body_result
from body.exceptions import (
    BodyDocxError,
    BodyImageError,
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
)
from body.images import collect_image_hrefs
from body.utils import body_from_docx_upload


class BodyViewSet(GenericViewSet):
    serializer_class = BodyMarkRequestSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if getattr(self, "action", None) == "docx":
            return BodyDocxRequestSerializer
        return BodyMarkRequestSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, Mapping):
            return JsonResponse({"error": "Error processing"}, status=400)

        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            return JsonResponse(serializer.errors, status=400)

        return self.mark_and_respond(
            serializer.validated_data["body"],
            serializer.validated_data.get("type", "json"),
            serializer.validated_data.get("language") or None,
            images=serializer.validated_data.get("images"),
            images_zip=serializer.validated_data.get("images_zip"),
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
            body_text, tables, figures = body_from_docx_upload(uploaded)
        except BodyDocxError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return self.mark_and_respond(
            body_text,
            output_type,
            language,
            tables=tables,
            figures=figures,
            images=serializer.validated_data.get("images"),
            images_zip=serializer.validated_data.get("images_zip"),
        )

    def mark_and_respond(
        self,
        body_text,
        output_type,
        language,
        tables=None,
        figures=None,
        images=None,
        images_zip=None,
    ):
        if not str(body_text or "").strip():
            return JsonResponse({"error": "No body provided"}, status=400)
        try:
            image_hrefs = collect_image_hrefs(images, images_zip)
        except BodyImageError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        try:
            result = resolve_body_result(
                body_text,
                user=self.request.user,
                output_type=output_type,
                language=language,
                tables=tables,
                figures=figures,
                image_hrefs=image_hrefs,
            )
        except (
            BodyLlamaDisabledError,
            BodyLlamaMisconfiguredError,
            BodyLlamaUnavailableError,
        ) as exc:
            return JsonResponse(
                {"error": f"Llama model is not available: {exc}"},
                status=503,
            )
        return JsonResponse(result)
