"""Версионируемые промпты из ``llm/prompts/<name>.md``.

Формат файла: строка-комментарий с версией, затем секции ``## system`` и ``## user``.
Подстановки — ``$name``, ``$text`` (``string.Template``, чтобы не конфликтовать с JSON).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from string import Template

_VERSION_RE = re.compile(r"version:\s*(\S+)")
_SECTION_RE = re.compile(r"^## (system|user)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: str
    system: str
    user: Template

    def render(self, **values: str) -> tuple[str, str]:
        return self.system, self.user.substitute(values)


@cache
def load_prompt(name: str) -> Prompt:
    text = resources.files("ipdl.llm").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")
    version_match = _VERSION_RE.search(text.splitlines()[0] if text else "")
    parts = _SECTION_RE.split(text)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if "system" not in sections or "user" not in sections:
        raise ValueError(f"Промпт {name}: нужны секции «## system» и «## user»")
    return Prompt(
        name=name,
        version=version_match.group(1) if version_match else "0",
        system=sections["system"],
        user=Template(sections["user"]),
    )
