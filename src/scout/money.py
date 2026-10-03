"""How scout writes amounts of money in the chat.

scout keeps money as whole cents so shares and payments add up exactly.
"""

CENTS_PER_DOLLAR = 100


def format_usd(cents: int) -> str:
    """Formats cents the way people text money: $1,240 or $236.50."""
    dollars, leftover_cents = divmod(cents, CENTS_PER_DOLLAR)
    if leftover_cents == 0:
        return f"${dollars:,}"
    return f"${dollars:,}.{leftover_cents:02d}"
