from __future__ import annotations

import tomllib

from dataclasses import dataclass
from pathlib import Path


from .utils import *


@dataclass(frozen=True)
class EmailConfig:
    provider: str
    username: str
    recipient: str

    smtp_host: str
    smtp_port: int
    smtp_security: str


def load_email_config() -> EmailConfig:
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Configuração não encontrada: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open("rb") as file:
        data = tomllib.load(file)

    email = data["email"]
    smtp = data["smtp"]

    return EmailConfig(
        provider=email["provider"],
        username=email["username"],
        recipient=email["recipient"],
        smtp_host=smtp["host"],
        smtp_port=smtp["port"],
        smtp_security=smtp["security"],
    )