from kargah.adapters.toml_config import parse_project_config
from kargah.domain.pricing import ModelPrice


def test_pricing_and_retention_come_from_the_config():
    cfg = parse_project_config("[pricing.\"claude-sonnet-5-5\"]\ninput = 3.0\noutput = 15.0\ncached = 0.3\n"
                               "[runs]\nkeep_days = 7\n")
    assert cfg.prices == {"claude-sonnet-5-5": ModelPrice(3.0, 15.0, 0.3)}
    assert cfg.runs_keep_days == 7


def test_a_price_without_output_is_a_config_error():
    import pytest

    from kargah.errors import KargahError
    with pytest.raises(KargahError):
        parse_project_config('[pricing."m"]\ninput = 1.0\n')


def test_defaults():
    cfg = parse_project_config(None)
    assert cfg.prices == {} and cfg.runs_keep_days == 30
