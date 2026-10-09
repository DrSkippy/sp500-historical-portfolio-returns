"""Return arithmetic shared by the models and the report scripts."""


def simple_return(start_price: float, end_price: float) -> float:
    """Fractional change from ``start_price`` to ``end_price`` (-0.1 for a 10% loss)."""
    return (end_price - start_price) / start_price
