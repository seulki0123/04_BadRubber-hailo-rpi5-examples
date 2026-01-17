from fractions import Fraction

def float_to_fraction_str(
    value: float,
    max_denominator: int = 1001,
) -> str:
    """
    Convert a float to a fraction string (e.g. for GStreamer caps).

    Examples:
        12.5    -> "25/2"
        29.97   -> "30000/1001"
        1.3333  -> "4/3"
    """
    if value <= 0:
        raise ValueError(f"Invalid value: {value}")

    frac = Fraction(value).limit_denominator(max_denominator)
    return f"{frac.numerator}/{frac.denominator}"