from cart import Cart


def test_item_count():
    cart = Cart()
    cart.add("pen", 2, quantity=3)
    cart.add("book", 10)
    assert cart.item_count() == 4


def test_subtotal_with_discount():
    cart = Cart()
    cart.add("book", 20, quantity=2, discount_percent=25)
    assert cart.subtotal() == 30


def test_total_with_tax():
    cart = Cart(tax_rate=0.10)
    cart.add("pen", 10, quantity=2)
    assert cart.total() == 22
