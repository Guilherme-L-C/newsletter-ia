"""Item coletado de uma fonte."""

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    fonte: str
    fonte_tipo: str
    titulo: str
    url: str
    data_publicacao: str
    resumo_bruto: str


_ARXIV = re.compile(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/(.+?)(?:v\d+)?(?:\.pdf)?$")


def item_id(url: str) -> str:
    norm = url.strip().split("#", 1)[0].rstrip("/").lower()
    if m := _ARXIV.match(norm):  # abs/pdf, vN e http viram o mesmo paper
        norm = f"https://arxiv.org/abs/{m.group(1)}"
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def data_ou_agora(valor: str | None) -> str:
    """ISO 8601 UTC do valor; sem data ou data inválida, a hora atual."""
    from datetime import datetime, timezone

    try:
        d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except (AttributeError, ValueError):
        return datetime.now(timezone.utc).isoformat()
