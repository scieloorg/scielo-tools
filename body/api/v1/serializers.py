from rest_framework import serializers

OUTPUT_TYPE_CHOICES = ["json", "xml"]


class BodyImageUploadSerializer(serializers.Serializer):
    images = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        default=list,
        help_text="Imagens fig-N.tif/jpg (campo repetível).",
    )
    images_zip = serializers.FileField(
        required=False,
        allow_null=True,
        help_text="Zip com figuras fig-N.tif/jpg.",
    )

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
            if hasattr(data, "_mutable"):
                data._mutable = True
            data.pop("images", None)
        elif isinstance(data, dict):
            data = dict(data)
            data.pop("images", None)
        ret = super().to_internal_value(data)
        request = self.context.get("request")
        if request is not None:
            ret["images"] = list(request.FILES.getlist("images"))
        else:
            ret.setdefault("images", [])
        return ret

    def validate_images_zip(self, value):
        if value is None:
            return value
        name = (getattr(value, "name", "") or "").lower()
        if not name.endswith(".zip"):
            raise serializers.ValidationError("Only .zip files are accepted.")
        if getattr(value, "size", None) == 0:
            raise serializers.ValidationError("Empty file.")
        return value


class BodyMarkRequestSerializer(BodyImageUploadSerializer):
    body = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
        help_text="Texto do corpo do artigo a marcar.",
    )
    type = serializers.ChoiceField(
        choices=OUTPUT_TYPE_CHOICES,
        default="json",
        required=False,
        help_text="Formato de saída: json ou xml.",
    )
    language = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Idioma principal do artigo (ex.: pt, en, es).",
    )


class BodyDocxRequestSerializer(BodyImageUploadSerializer):
    file = serializers.FileField(
        help_text="Arquivo .docx com o corpo do artigo.",
    )
    type = serializers.ChoiceField(
        choices=OUTPUT_TYPE_CHOICES,
        default="json",
        required=False,
        help_text="Formato de saída: json ou xml.",
    )
    language = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Idioma principal do artigo (ex.: pt, en, es).",
    )

    def validate_file(self, value):
        name = (getattr(value, "name", "") or "").lower()
        if not name.endswith(".docx"):
            raise serializers.ValidationError("Only .docx files are accepted.")
        if getattr(value, "size", None) == 0:
            raise serializers.ValidationError("Empty file.")
        return value
