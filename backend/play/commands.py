from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedPlayInput:
    raw: str
    command: Optional[str]
    argument: str

    @property
    def is_command(self) -> bool:
        return self.command is not None


def parse_play_input(value: str) -> ParsedPlayInput:
    raw = value.strip()
    if not raw.startswith("/"):
        return ParsedPlayInput(raw=raw, command=None, argument=raw)

    command_text = raw[1:]
    command, _, argument = command_text.partition(" ")
    return ParsedPlayInput(
        raw=raw,
        command=command.lower(),
        argument=argument.strip(),
    )
