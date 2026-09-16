from body.providers.http import Provider


def get_provider(messages, response_format, **kwargs):
    return Provider(messages, response_format, **kwargs)
