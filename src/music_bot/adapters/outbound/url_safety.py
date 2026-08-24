from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from time import perf_counter
from urllib.parse import SplitResult, urlsplit

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

logger: logging.Logger = logging.getLogger(__name__)


class UnsafeUrlError(Exception):
    pass


def _is_unsafe_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not address.is_global


async def ensure_safe_url(source_url: str) -> None:
    parsed: SplitResult = urlsplit(source_url)
    logger.debug(
        "URL safety check started scheme=%r hostname=%r",
        parsed.scheme,
        parsed.hostname,
    )
    if parsed.scheme not in _ALLOWED_SCHEMES:
        logger.info("URL safety rejected unsupported scheme=%r", parsed.scheme)
        raise UnsafeUrlError("Only http/https links are supported.")
    if parsed.username is not None or parsed.password is not None:
        logger.info("URL safety rejected embedded credentials hostname=%r", parsed.hostname)
        raise UnsafeUrlError("Credentials in URLs are not supported.")

    hostname: str | None = parsed.hostname
    if hostname is None:
        logger.info("URL safety rejected missing hostname scheme=%s", parsed.scheme)
        raise UnsafeUrlError("That URL has no host.")

    try:
        port: int | None = parsed.port
    except ValueError as exc:
        logger.info("URL safety rejected invalid port hostname=%r", hostname)
        raise UnsafeUrlError("That URL has an invalid port.") from exc

    expected_port: int = 443 if parsed.scheme == "https" else 80
    if port is not None and port != expected_port:
        logger.info(
            "URL safety rejected unsupported port hostname=%r port=%s expected_port=%s",
            hostname,
            port,
            expected_port,
        )
        raise UnsafeUrlError("That URL uses an unsupported port.")
    logger.debug(
        "URL shape accepted scheme=%s hostname=%r port=%s",
        parsed.scheme,
        hostname,
        port or expected_port,
    )

    try:
        literal_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = (
            ipaddress.ip_address(hostname)
        )
    except ValueError:
        literal_address = None

    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    if literal_address is not None:
        logger.debug("URL host is an IP literal hostname=%r", hostname)
        addresses = (literal_address,)
    else:
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        started_at: float = perf_counter()
        logger.debug(
            "DNS resolution started hostname=%r port=%s socket_type=STREAM",
            hostname,
            port or expected_port,
        )
        try:
            resolved: list[
                tuple[
                    socket.AddressFamily,
                    socket.SocketKind,
                    int,
                    str,
                    tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
                ]
            ] = await loop.getaddrinfo(
                hostname,
                port or expected_port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            logger.warning(
                "DNS resolution failed hostname=%r error=%s",
                hostname,
                exc,
            )
            raise UnsafeUrlError("That URL's host could not be resolved.") from exc

        address_values: list[str] = []
        for resolved_item in resolved:
            raw_address: str | int = resolved_item[4][0]
            if isinstance(raw_address, str):
                logger.debug(
                    "DNS answer hostname=%r family=%s socket_type=%s address=%s",
                    hostname,
                    resolved_item[0].name,
                    resolved_item[1].name,
                    raw_address,
                )
                address_values.append(raw_address)

        logger.debug(
            "DNS resolution completed hostname=%r answers=%s elapsed_ms=%.2f",
            hostname,
            len(address_values),
            (perf_counter() - started_at) * 1000,
        )

        addresses = tuple(ipaddress.ip_address(value) for value in address_values)

    if not addresses:
        logger.info("URL safety rejected host with no addresses hostname=%r", hostname)
        raise UnsafeUrlError("That URL cannot be used.")

    unsafe_found: bool = False
    for address in addresses:
        unsafe: bool = _is_unsafe_address(address)
        logger.debug(
            "IP safety result hostname=%r address=%s version=%s is_global=%s accepted=%s",
            hostname,
            address,
            address.version,
            address.is_global,
            not unsafe,
        )
        unsafe_found = unsafe_found or unsafe

    if unsafe_found:
        logger.info(
            "URL safety rejected non-global address hostname=%r addresses=%s",
            hostname,
            ",".join(str(address) for address in addresses),
        )
        raise UnsafeUrlError("That URL cannot be used.")

    logger.debug(
        "URL safety check passed hostname=%r addresses=%s",
        hostname,
        ",".join(str(address) for address in addresses),
    )
