from __future__ import annotations

import pytest

from app.unifi.types import (
    is_unicast_mac,
    normalize_host,
    normalize_mac,
    validate_device_mac,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
        ("aa-bb-cc-dd-ee-ff", "aa:bb:cc:dd:ee:ff"),
        ("aabbccddeeff", "aa:bb:cc:dd:ee:ff"),
        ("  Aa:Bb:Cc:Dd:Ee:Ff  ", "aa:bb:cc:dd:ee:ff"),
    ],
)
def test_normalize_mac(raw, expected):
    assert normalize_mac(raw) == expected


@pytest.mark.parametrize("raw", ["", "aa:bb:cc:dd:ee", "zz:bb:cc:dd:ee:ff", "aabbccddeeff00"])
def test_normalize_mac_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_mac(raw)


def test_multicast_and_broadcast_rejected():
    assert is_unicast_mac("aa:bb:cc:dd:ee:ff")
    assert not is_unicast_mac("01:00:5e:00:00:01")
    assert not is_unicast_mac("ff:ff:ff:ff:ff:ff")
    with pytest.raises(ValueError):
        validate_device_mac("01:00:5e:00:00:01")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.1.1", "https://192.168.1.1"),
        ("https://udm.local/", "https://udm.local"),
        ("https://udm.local:443", "https://udm.local:443"),
        ("https://udm.local/proxy/network/integration/v1", "https://udm.local"),
        ("https://udm.local/proxy/network/api/s/default", "https://udm.local"),
        ("https://example.com/unifi/", "https://example.com/unifi"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ],
)
def test_normalize_host(raw, expected):
    assert normalize_host(raw) == expected


@pytest.mark.parametrize("raw", ["ftp://udm.local", "https://", "://bad"])
def test_normalize_host_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_host(raw)
