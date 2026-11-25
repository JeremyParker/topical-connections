import logging
from typing import Protocol

import httpx

from .config import Settings, Topic

log = logging.getLogger("uvicorn.error")


class MailError(Exception):
    pass


class Mailer(Protocol):
    def send_login_code(self, topic: Topic, to: str, code: str) -> None: ...


class ConsoleMailer:
    """Development only: prints the code instead of emailing it."""

    def send_login_code(self, topic: Topic, to: str, code: str) -> None:
        log.info("[%s] login code for %s: %s", topic.name, to, code)


class ResendMailer:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def send_login_code(self, topic: Topic, to: str, code: str) -> None:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": topic.email_from,
                    "to": [to],
                    "subject": f"Your {topic.name} sign-in code",
                    "text": (
                        f"Your {topic.name} sign-in code is {code}\n\n"
                        "It expires in 10 minutes. If you didn't ask for it, "
                        "you can ignore this email."
                    ),
                },
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise MailError(str(e)) from e


def make_mailer(settings: Settings) -> Mailer:
    if settings.email_backend == "console":
        return ConsoleMailer()
    return ResendMailer(settings.resend_api_key)
