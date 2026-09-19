import keyring


from .utils import *


def save_email_password(
    username: str,
    password: str,
) -> None:
    keyring.set_password(
        SERVICE_NAME,
        username,
        password,
    )


def get_email_password(
    username: str,
) -> str:
    password = keyring.get_password(
        SERVICE_NAME,
        username,
    )

    if password is None:
        raise RuntimeError(
            "Senha de e-mail não configurada."
        )

    return password


def delete_email_password(
    username: str,
) -> None:
    keyring.delete_password(
        SERVICE_NAME,
        username,
    )