from rest_framework import serializers

OUTPUT_TYPE_CHOICES = ["json", "xml"]


class BodyMarkRequestSerializer(serializers.Serializer):
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


class BodyDocxRequestSerializer(serializers.Serializer):
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
