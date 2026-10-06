"""Safe failures shared by HTTP, database and operating boundaries."""

from dataclasses import dataclass


@dataclass(eq=False)
class Rejected(ValueError):
    code: str
    message: str
    status: int = 400
    fields: tuple[str, ...] = ()

    def __post_init__(self):
        super().__init__(self.message)

    def public(self):
        return {"code": self.code, "message": self.message,
                "fields": list(self.fields)}


def invalid(field="settings"):
    return Rejected("invalid_input", "Please check the highlighted information.",
                    fields=(field,))


def unavailable():
    return Rejected("temporarily_unavailable",
                    "We could not complete this request. Please try again.", 503)
