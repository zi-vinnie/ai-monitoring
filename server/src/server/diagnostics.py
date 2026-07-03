import subprocess
from collections.abc import Callable
from urllib.parse import urlparse


def ping(host: str, timeout_s: float = 2.0) -> bool:
    """Return True if ``host`` answers a single ICMP echo.

    Shells out to the system ``ping`` binary so no raw-socket privileges are
    needed. Any failure (host unreachable, name won't resolve, ``ping`` missing)
    yields False rather than raising, so callers can treat it as a plain probe.
    """
    # -c 1: one echo request. -W: per-reply timeout in whole seconds (Linux).
    wait = str(max(1, round(timeout_s)))
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", wait, host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s + 2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def agent_host(agent_url: str) -> str | None:
    """Extract the bare hostname/IP from an AGENT_URL (for pinging)."""
    return urlparse(agent_url).hostname


def diagnose_unreachable(
    agent_url: str,
    router_ip: str | None,
    ping_fn: Callable[[str], bool] = ping,
) -> tuple[str, str]:
    """Classify why a /screenshot call failed at the socket level.

    Reached only when we couldn't get *any* HTTP response (connection refused,
    timeout). ICMP probes tell the three routine causes apart so the logs say
    which one actually happened instead of a bare "unreachable":

      * router/Wi-Fi is down .............................. "network_down"
      * machine is on but the agent isn't answering ....... "agent_down"
      * machine is off, asleep, or off the network ........ "unreachable"

    The router probe is what disambiguates the last two: without ``router_ip``
    configured a downed router looks identical to a powered-off machine, so we
    fall back to a host-only guess and say so.
    """
    if router_ip and not ping_fn(router_ip):
        return "network_down", f"router {router_ip} did not answer ping; Wi-Fi/router likely down"

    host = agent_host(agent_url)
    if host and ping_fn(host):
        return (
            "agent_down",
            f"{host} answers ping but the agent port is unreachable; "
            "machine is on but the agent is stopped or firewalled",
        )
    return "unreachable", f"{host or agent_url} did not answer ping; machine off, asleep, or off-network"
