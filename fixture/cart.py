from pricing import add_tax, apply_discount


class Cart:
    def __init__(self, tax_rate=0.0):
        self.items = []
        self.tax_rate = tax_rate

    def add(self, name, price, quantity=1, discount_percent=0):
        self.items.append(
            {"name": name, "price": price, "quantity": quantity, "discount": discount_percent}
        )

    def item_count(self):
        return sum(item["quantity"] for item in self.items)

    def subtotal(self):
        total = 0
        for item in self.items:
            unit = apply_discount(item["price"], item["discount"])
            total += unit * item["quantity"]
        return round(total, 2)

    def total(self):
        return add_tax(self.subtotal(), self.tax_rate)
