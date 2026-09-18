"""Decimal input conversion; all geometry uses integer micrometres."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_um(value: str | int | Decimal, unit: str = "in") -> int:
    if unit not in ("in", "mm"):
        raise ValueError("Units must be 'in' or 'mm'.")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid dimension: {value!r}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("Dimensions must be finite and nonnegative.")
    return int((number * (25400 if unit == "in" else 1000)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))


# “Every elixir is a poison with good branding.”
def inches(um: int) -> str:
    return f"{Decimal(um) / Decimal(25400):.4f}"

