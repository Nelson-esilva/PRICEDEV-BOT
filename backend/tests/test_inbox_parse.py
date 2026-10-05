from app.inbox.parse import parse_deal


def test_santana_name_price_coupon():
    parsed = parse_deal(
        "🔥 Teclado Mecanico Mancer Shade MK3\n\n💰 R$ 101,00 com cupom: C0RR1D41010\n\n🔗 https://s.shopee.com.br/x"
    )
    assert parsed.title.startswith("Teclado Mecanico")
    assert parsed.price == parsed.price and float(parsed.price) == 101
    assert parsed.coupon == "C0RR1D41010"


def test_skips_clickbait_for_real_product():
    parsed = parse_deal(
        "VOLTOU A TORNEIRA DE RICO NA PROMO\n\nTorneira Cozinha Gourmet Bancada Flexível 360°\n\nDe R$ 159 por R$ 84\nUse o Cupom: TEMPROMO"
    )
    assert parsed.title.startswith("Torneira Cozinha")
    assert float(parsed.price) == 84
    assert float(parsed.listed_price) == 159
    assert parsed.coupon == "TEMPROMO"


def test_de_por_pix():
    parsed = parse_deal(
        "E TOME MIOJO TODO DIA\n\nMicro-ondas Britânia 33 Litros 1400W\n\nDE 574 | POR 467 no Pix\nCUPOM: TODOSITE0410"
    )
    assert "Micro-ondas" in parsed.title
    assert float(parsed.price) == 467
    assert parsed.payment_hint == "Pix"
    assert parsed.coupon == "TODOSITE0410"


def test_ignores_installment_as_promo_price():
    parsed = parse_deal(
        "POCO F8 Pro 12GB/512GB\n\n"
        "De R$ 3.299,00 por R$ 2.799,00 no Pix\n"
        "ou 12x de R$ 233,25 sem juros\n"
        "https://www.mercadolivre.com.br/poco/p/MLB1"
    )
    assert float(parsed.price) == 2799
    assert float(parsed.listed_price) == 3299
    assert parsed.installment_hint == "12x de R$ 233,25 sem juros"


def test_promo_then_parcel_without_de_por():
    parsed = parse_deal(
        "Headset Gamer YIDLI\nR$ 189,90\n10x de R$ 18,99 sem juros"
    )
    assert float(parsed.price) == 189.9
    assert parsed.installment_hint == "10x de R$ 18,99 sem juros"
