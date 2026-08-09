"""Geração do feed iCal (RFC 5545) — spec 037, regra 5.

Funções puras: recebem eventos já filtrados e o timezone da conta, devolvem o texto
`.ics`. A validação nos testes é por parser (biblioteca `icalendar`), nunca por
comparação de string.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_UID_DOMAIN = "rito.local"
_TTL = "PT1H"
_LINE_LIMIT = 75  # octetos por linha física, RFC 5545 §3.1


@dataclass
class ICalEvent:
    """O mínimo que um VEVENT precisa — o service monta a partir das linhas da agenda."""

    post_id: uuid.UUID
    summary: str
    day: date
    start_time: time | None
    end_day: date | None
    end_time: time | None
    all_day: bool
    location: str | None


def _escape(text: str) -> str:
    """Escapes do valor TEXT (RFC 5545 §3.3.11): barra primeiro, depois ; , e quebra."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Dobra linhas acima de 75 octetos com CRLF + espaço (RFC 5545 §3.1)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= _LINE_LIMIT:
        return line
    chunks: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        if current_len + char_len > _LINE_LIMIT:
            chunks.append(current)
            current = " " + char
            current_len = 1 + char_len
        else:
            current += char
            current_len += char_len
    chunks.append(current)
    return "\r\n".join(chunks)


def _to_utc(day: date, moment: time, timezone: ZoneInfo) -> datetime:
    """Data/hora local da conta → UTC (regra 5: datas do feed em UTC)."""
    return datetime.combine(day, moment, tzinfo=timezone).astimezone(UTC)


def _format_dt(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _format_day(day: date) -> str:
    return day.strftime("%Y%m%d")


def _event_lines(event: ICalEvent, timezone: ZoneInfo, stamp: datetime) -> list[str]:
    # UID estável por tarefa (regra 5): reprocessar o feed não duplica o evento no
    # calendário do usuário.
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.post_id}@{_UID_DOMAIN}",
        f"DTSTAMP:{_format_dt(stamp)}",
        f"SUMMARY:{_escape(event.summary)}",
    ]
    if event.all_day or event.start_time is None:
        # Dia inteiro: DATE sem hora; DTEND exclusivo = dia seguinte (RFC 5545 §3.6.1).
        end_day = event.end_day or event.day
        lines.append(f"DTSTART;VALUE=DATE:{_format_day(event.day)}")
        lines.append(f"DTEND;VALUE=DATE:{_format_day(end_day + timedelta(days=1))}")
    else:
        lines.append(f"DTSTART:{_format_dt(_to_utc(event.day, event.start_time, timezone))}")
        if event.end_day is not None and event.end_time is not None:
            lines.append(f"DTEND:{_format_dt(_to_utc(event.end_day, event.end_time, timezone))}")
        else:
            # Sem término explícito: slot de 1h (regra 4 — com hora, ocupa o slot).
            end = _to_utc(event.day, event.start_time, timezone) + timedelta(hours=1)
            lines.append(f"DTEND:{_format_dt(end)}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    lines.append("END:VEVENT")
    return lines


def build_ical(events: list[ICalEvent], *, timezone_name: str, calendar_name: str) -> str:
    """Monta o VCALENDAR completo com CRLF e os cabeçalhos de refresh (regra 5)."""
    timezone = ZoneInfo(timezone_name)
    stamp = datetime.now(UTC)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Rito//Agenda//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        f"X-PUBLISHED-TTL:{_TTL}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{_TTL}",
    ]
    for event in events:
        lines.extend(_event_lines(event, timezone, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
