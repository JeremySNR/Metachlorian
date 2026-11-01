"""Read ISO and ExifTool capture dates without changing stored source metadata."""

from datetime import datetime


def capture_iso(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) >= 10 and value[4] == ':' and value[7] == ':':
        value = value[:10].replace(':', '-') + value[10:]
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat()
    except ValueError:
        return None


def _capture_text_sql(column: str) -> str:
    # column is a trusted SQL expression, never user input. Keep sorting in SQL
    # so dates are ordered across the whole library before pagination.
    return (f"(CASE WHEN substr(trim({column}),5,1)=':' AND substr(trim({column}),8,1)=':' "
            f"THEN replace(substr(trim({column}),1,10),':','-') || substr(trim({column}),11) ELSE trim({column}) END)")


def capture_calendar_sql(column: str) -> str:
    """The valid calendar day recorded by the camera, without shifting its timezone."""
    text = _capture_text_sql(column)
    day = f"substr({text},1,10)"
    return (f"(CASE WHEN {day} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
            f"AND CAST(substr({day},1,4) AS INTEGER)>0 AND date({day},'+0 days')={day} "
            f"AND julianday({text}) IS NOT NULL THEN {day} END)")


def capture_day_sql(column: str) -> str:
    """A sortable timestamp for ISO or legacy Exif dates; invalid metadata is unknown."""
    return f"(CASE WHEN {capture_calendar_sql(column)} IS NOT NULL THEN julianday({_capture_text_sql(column)}) END)"
