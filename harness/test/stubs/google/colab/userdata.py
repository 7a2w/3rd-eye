import os


class SecretNotFoundError(Exception):
    pass


def get(name):
    value = os.environ.get("TE_SECRET_" + name)
    if value is None:
        raise SecretNotFoundError(name)
    return value
