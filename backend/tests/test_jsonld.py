from decimal import Decimal

from app.ingestion.jsonld import parse_jsonld_product


def test_reads_product_offer():
    html = """
    <html><script type="application/ld+json">
    {"@type":"Product","name":"SSD 1TB","image":"https://img.example/ssd.jpg",
     "offers":{"@type":"Offer","price":"199.90","priceCurrency":"BRL","availability":"https://schema.org/InStock"}}
    </script></html>
    """
    parsed = parse_jsonld_product(html)
    assert parsed is not None
    assert parsed.name == "SSD 1TB"
    assert parsed.price == Decimal("199.90")
    assert parsed.availability == "in_stock"


def test_skips_financing_and_keeps_cash_price():
    html = """
    <script type="application/ld+json">
    {"@type":"Product","name":"TV",
     "offers":[
       {"@type":"Offer","price":"80","priceType":"Monthly financing"},
       {"@type":"Offer","price":"1999.00","priceCurrency":"BRL"}
     ]}
    </script>
    """
    parsed = parse_jsonld_product(html)
    assert parsed is not None
    assert parsed.price == Decimal("1999.00")
