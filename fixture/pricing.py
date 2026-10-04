def apply_discount(price, percent):
    """Return price after taking `percent` off (percent is 0-100)."""
    discounted = price - price * percent
    return round(discounted, 2)


def add_tax(price, rate):
    """Return price with a tax rate added (rate is a fraction, e.g. 0.13)."""
    taxed = price * (1 + rate)
    return round(taxed, 2)
