from __future__ import annotations

import logging
import socket

import pytest

from music_bot.adapters.outbound.url_safety import UnsafeUrlError, ensure_safe_url

type AddressInfo = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    str,
    tuple[str, int],
]


@pytest.mark.unit
class TestEnsureSafeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/track",
            "https://user:password@example.com/track",
            "https://example.com:8443/track",
            "https://example.com:invalid/track",
            "https:///track-without-host",
        ],
    )
    async def test_rejects_unsafe_shape(self, url: str) -> None:
        with pytest.raises(UnsafeUrlError):
            await ensure_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/track",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/track",
        ],
    )
    async def test_rejects_literal_private_address(self, url: str) -> None:
        with pytest.raises(UnsafeUrlError):
            await ensure_safe_url(url)

    async def test_rejects_hostname_resolving_to_private_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)

        with pytest.raises(UnsafeUrlError):
            await ensure_safe_url("https://youtube.com/track")

    async def test_rejects_hostname_when_any_resolved_address_is_private(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
            ]

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)

        with pytest.raises(UnsafeUrlError):
            await ensure_safe_url("https://youtube.com/track")

    async def test_rejects_hostname_with_no_resolved_addresses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            return []

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)

        with pytest.raises(UnsafeUrlError):
            await ensure_safe_url("https://youtube.com/track")

    async def test_translates_dns_resolution_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            raise socket.gaierror("not found")

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)

        with pytest.raises(UnsafeUrlError, match="could not be resolved"):
            await ensure_safe_url("https://youtube.com/track")

    async def test_allows_hostname_resolving_to_public_address(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)

        await ensure_safe_url("https://youtube.com/track")

    async def test_logs_every_dns_answer_and_ip_safety_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async def getaddrinfo(
            host: str, port: object, *args: object, **kwargs: object
        ) -> list[AddressInfo]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0)),
            ]

        monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", getaddrinfo)
        caplog.set_level(logging.DEBUG)

        await ensure_safe_url("https://youtube.com/watch?v=secret")

        messages: list[str] = [record.getMessage() for record in caplog.records]
        assert any("DNS answer" in message and "8.8.8.8" in message for message in messages)
        assert any("DNS answer" in message and "1.1.1.1" in message for message in messages)
        assert any(
            "IP safety result" in message and "8.8.8.8" in message and "accepted=True" in message
            for message in messages
        )
        assert any("URL safety check passed" in message for message in messages)
        assert all("secret" not in message for message in messages)
