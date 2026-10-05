from decimal import Decimal

from app.pricing.outlier import ReadVerdict, classify_read, reads_agree


def test_short_history_is_accepted():
    decision = classify_read(Decimal("10"), [Decimal("10")] * 3)
    assert decision.verdict is ReadVerdict.ACCEPT


def test_absurd_low_is_rejected():
    history = [Decimal("500")] * 8
    decision = classify_read(Decimal("5"), history)
    assert decision.verdict is ReadVerdict.REJECT


def test_steep_but_possible_drop_is_held():
    history = [Decimal("500")] * 8
    decision = classify_read(Decimal("200"), history)
    assert decision.verdict is ReadVerdict.CONFIRM


def test_normal_drop_is_accepted():
    history = [Decimal("500")] * 8
    decision = classify_read(Decimal("400"), history)
    assert decision.verdict is ReadVerdict.ACCEPT


def test_zero_allowed_for_coupon():
    decision = classify_read(Decimal("0"), [Decimal("100")] * 8, allow_zero=True)
    assert decision.verdict is ReadVerdict.ACCEPT


def test_reads_agree_within_two_percent():
    assert reads_agree(Decimal("100.00"), Decimal("101.50"))
    assert not reads_agree(Decimal("100.00"), Decimal("120.00"))
