from rest_framework import serializers

OUTPUT_TYPE_CHOICES = ["json", "xml", "jats"]


class ReferencesInputField(serializers.Field):
    def __init__(self, **kwargs):
        kwargs.setdefault("style", {"base_template": "textarea.html", "rows": 10})
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value


class ReferenceMarkRequestSerializer(serializers.Serializer):
    references = ReferencesInputField(
        help_text=(
            'Uma referência por linha, lista JSON ["Ref A", "Ref B"] ou string única.'
        ),
    )
    type = serializers.ChoiceField(
        choices=OUTPUT_TYPE_CHOICES,
        default="json",
        required=False,
        help_text="Formato de saída: json, xml ou jats.",
    )


class ReferenceDocxRequestSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="Arquivo .docx com secção de referências.",
    )
    type = serializers.ChoiceField(
        choices=OUTPUT_TYPE_CHOICES,
        default="json",
        required=False,
        help_text="Formato de saída: json, xml ou jats.",
    )

    def validate_file(self, value):
        name = (getattr(value, "name", "") or "").lower()
        if not name.endswith(".docx"):
            raise serializers.ValidationError("Only .docx files are accepted.")
        if getattr(value, "size", None) == 0:
            raise serializers.ValidationError("Empty file.")
        return value
