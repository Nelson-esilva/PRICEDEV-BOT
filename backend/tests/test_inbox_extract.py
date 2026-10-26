from app.inbox.extract import (
    describe_link,
    extract_coupon_links,
    extract_image_urls,
    extract_urls,
    inbox_campaign_key,
    inbox_identity_key,
    is_coupon_mechan,
    needs_resolve,
    pick_product_url,
    title_from_text,
)
from app.inbox.media import amazon_image, catalog_image


def test_picks_store_link_over_telegram():
    urls = extract_urls(
        "SSD em oferta https://t.me/grupo https://www.kabum.com.br/produto/123456/ssd-1tb"
    )
    assert pick_product_url(urls) == "https://www.kabum.com.br/produto/123456/ssd-1tb"


def test_title_ignores_bare_url_line():
    title = title_from_text("https://shopee.com.br/x\nSSD NVMe 1TB com cupom")
    assert title.startswith("SSD NVMe")


def test_ignores_message_without_store_link():
    urls = extract_urls("só conversa no grupo https://t.me/achadinhos")
    assert pick_product_url(urls) is None


def test_keeps_affiliate_short_links():
    urls = extract_urls("oferta https://amzn.to/abc123 https://bit.ly/xyz https://dpl.pelando.com.br/abc")
    assert any("amzn.to" in item for item in urls)
    assert any("bit.ly" in item for item in urls)
    assert any("dpl.pelando" in item for item in urls)
    assert pick_product_url(urls) is not None
    assert needs_resolve("https://amzn.to/abc123") is True


def test_extracts_coupon_links_after_resgate_block():
    text = (
        "Cooktop Itatiaia Essencial 4 Bocas Preto\n"
        "🔥 R$ 234 no PIX\n"
        "https://s.shopee.com.br/produtoCooktop\n"
        "🎟️ Resgate todos os cupons\n"
        "1. https://s.shopee.com.br/8AWstpqRdH\n"
        "2. https://s.shopee.com.br/905ztMrfjp\n"
    )
    urls = extract_urls(text)
    product = "https://s.shopee.com.br/produtoCooktop"
    coupons = extract_coupon_links(text, urls, product)
    assert coupons == [
        "https://s.shopee.com.br/8AWstpqRdH",
        "https://s.shopee.com.br/905ztMrfjp",
    ]
    assert extract_coupon_links("só produto https://s.shopee.com.br/abc", urls, product) == []


def test_coupon_off_text_does_not_steal_product_link():
    text = (
        'Smart TV TCL 65"\n'
        "🔥 R$ 5.625 no PIX\n"
        "🏷 Aplique o cupom de R$300 OFF no anúncio\n"
        "🛒 Compre aqui: https://meli.la/2bWxsKt"
    )
    urls = extract_urls(text)
    assert extract_coupon_links(text, urls, "https://meli.la/2bWxsKt") == []


def test_detects_coupon_mechan_without_product():
    title = "10% OFF a partir de R$ 89, Limite de R$ 20: FULL1510"
    assert is_coupon_mechan(
        text=title,
        title=title,
        url="https://heylink.me/customer9725",
        native_id="",
    )
    assert not is_coupon_mechan(
        text='Smart TV TCL 65" R$ 5.625 no PIX',
        title="Smart TV TCL 65",
        url="https://www.mercadolivre.com.br/tv/p/MLB77168316",
        native_id="MLB77168316",
    )


def test_blocks_meli_coupon_banner_even_with_mlbu():
    """Campanha de cupom do canal: meli.la resolve pra MLBU, mas não é produto."""
    body = (
        "💸 Cupom Mercado Livre\n"
        "🏷️ 30% OFF a partir de R$ 1, Limite de R$ 10000: 3PROMOMELI30\n"
        "https://meli.la/2hbd5fB\n"
        "🤝 Entre nos links do canal e vá até seu produto\n"
        "https://heylink.me/customer9725\n"
    )
    title = "30% OFF a partir de R$ 1, Limite de R$ 10000: 3PROMOMELI30"
    assert is_coupon_mechan(
        text=body,
        title=title,
        url="https://www.mercadolivre.com.br/p/MLBU4828725477",
        native_id="MLBU4828725477",
    )
    assert is_coupon_mechan(
        text=title,
        title=title,
        url="https://meli.la/2hbd5fB",
        native_id="MLBU4828725477",
    )


def test_real_product_with_channel_footer_is_not_mechan():
    body = (
        'Samsung Combo Smart TV 43" QLED\n'
        "R$ 1801 Até 12x sem juros\n"
        "https://www.amazon.com.br/dp/B0GVW8464B\n"
        "📍conheça nossos Grupos de Ofertas e Redes sociais! https://heylink.me/customer9725\n"
    )
    assert not is_coupon_mechan(
        text=body,
        title='Samsung Combo Smart TV 43" QLED',
        url="https://www.amazon.com.br/dp/B0GVW8464B",
        native_id="B0GVW8464B",
    )


def test_aliexpress_prefers_pc_link_over_coins_and_heylink():
    text = (
        "ESTOQUE NO BRASIL\n"
        "R$ 251. Cupom: WOBR07\n"
        "Vai abrir a página de moedas, clique no primeiro produto (pelo app do celular):\n"
        "https://a.aliexpress.com/_c4IjZCtf\n"
        "Link PC (Preço pode ser maior):\n"
        "https://a.aliexpress.com/_c3ht2XVj\n"
        "https://heylink.me/customer9725\n"
    )
    urls = extract_urls(text)
    assert pick_product_url(urls, text) == "https://a.aliexpress.com/_c3ht2XVj"


def test_extracts_store_image_from_text():
    urls = extract_image_urls("foto https://http2.mlstatic.com/D_NQ_NP_123-O.webp oferta")
    assert urls == ["https://http2.mlstatic.com/D_NQ_NP_123-O.webp"]


def test_amazon_cover_from_asin():
    assert amazon_image("B0ABCDEFGH") == "https://m.media-amazon.com/images/P/B0ABCDEFGH.01.LZZZZZZZ.jpg"
    assert catalog_image(marketplace="amazon", native_id="B0ABCDEFGH", text="")


async def test_resolve_amazon_rejects_placeholder_gif(monkeypatch):
    from app.inbox import media as media_mod

    class _Resp:
        status_code = 200
        content = b"GIF89a" + b"\x00" * 37

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

        async def aclose(self):
            return None

    monkeypatch.setattr(media_mod.httpx, "AsyncClient", _Client)
    assert await media_mod.resolve_amazon_image("B0CJTB2QV2") is None


def test_prefers_resolved_store_over_shortener():
    urls = [
        "https://bit.ly/xyz",
        "https://www.kabum.com.br/produto/123456/ssd",
    ]
    assert pick_product_url(urls) == "https://www.kabum.com.br/produto/123456/ssd"
    assert describe_link("https://bit.ly/xyz")[0] == "afiliado"


def test_same_item_different_captions_share_identity():
    mlb = "https://www.mercadolivre.com.br/fone/p/MLB12345678?matt_word=a"
    other = "https://produto.mercadolivre.com.br/MLB12345678-fone-barato"
    assert inbox_identity_key("mercadolivre", "MLB12345678", mlb) == inbox_identity_key(
        "mercadolivre", "MLB12345678", other
    )
    assert inbox_identity_key("amazon", "B0ABCDEFGH", "https://www.amazon.com.br/dp/B0ABCDEFGH") == (
        "amazon:b0abcdefgh"
    )
    assert inbox_identity_key("unknown", "", mlb) == inbox_identity_key("unknown", "", other)
    assert inbox_identity_key("shopee", "", "https://s.shopee.com.br/7faRKeFnHI") == ""
    assert inbox_identity_key("shopee", "46054420959", "https://s.shopee.com.br/7faRKeFnHI") == (
        "shopee:46054420959"
    )
    assert inbox_identity_key("amazon", "", "https://www.amazon.com.br/dp/B0CNKVYLF5?tag=x") == (
        "amazon:b0cnkvylf5"
    )
    assert inbox_identity_key("amazon", "", "https://www.amazon.com.br/?tag=santanatech-20") == ""
    assert inbox_campaign_key(
        marketplace="amazon",
        title="10% OFF em R$ 400, máx de R$ 100 OFF: PRIMEHOJE",
        coupon="AMAZON",
        price=100,
        listed=400,
    ) == inbox_campaign_key(
        marketplace="amazon",
        title="10% OFF a partir de R$ 400, Limite de R$ 100 OFF: PRIMEHOJE",
        price=100,
        listed=400,
    )


def test_title_skips_checkout_instructions():
    from app.inbox.parse import parse_deal

    body = (
        "🥈 SÓ COMPRA NA FARMACIA SE DEIXAR O RIM\n⚠️desconto aplicado na finalização da compra\n\n"
        "Protetor Solar Facial Neutrogena Sun Fresh Derm Care Sem Cor FPS 70 40g\n\n"
        '💡selecione "Programe e Poupe"\npor 41,24 em 2x sem juros\nhttps://link.amazon/B06eMphNO'
    )
    assert parse_deal(body).title.startswith("Protetor Solar Facial Neutrogena")
