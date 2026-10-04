from pricing import add_tax, apply_discount


def test_apply_discount():
    assert apply_discount(100, 10) == 90


def test_apply_discount_zero():
    assert apply_discount(50, 0) == 50


def test_add_tax():
    assert add_tax(100, 0.13) == 113
