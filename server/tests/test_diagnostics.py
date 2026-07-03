from server.diagnostics import agent_host, diagnose_unreachable

AGENT_URL = "http://192.168.1.50:8000"
ROUTER = "192.168.1.1"


def _pinger(reachable):
    """Fake ping_fn: returns True only for hosts in the ``reachable`` set."""
    return lambda host: host in reachable


def test_agent_host_extracts_ip():
    assert agent_host("http://192.168.1.50:8000") == "192.168.1.50"


def test_agent_host_extracts_name():
    assert agent_host("http://desktop.local:8000/screenshot") == "desktop.local"


def test_router_down_reported_as_network_down():
    # Nothing on the LAN answers: blame the router/Wi-Fi, not the machine.
    status, detail = diagnose_unreachable(AGENT_URL, ROUTER, _pinger(set()))
    assert status == "network_down"
    assert ROUTER in detail


def test_router_up_but_machine_off_is_unreachable():
    status, detail = diagnose_unreachable(AGENT_URL, ROUTER, _pinger({ROUTER}))
    assert status == "unreachable"
    assert "192.168.1.50" in detail


def test_machine_up_but_agent_down():
    # Router and machine both answer ping, but the agent port refused the TCP
    # connection — the machine is on, the service isn't.
    status, detail = diagnose_unreachable(AGENT_URL, ROUTER, _pinger({ROUTER, "192.168.1.50"}))
    assert status == "agent_down"
    assert "192.168.1.50" in detail


def test_no_router_configured_falls_back_to_host_probe():
    # Without a router IP we can't distinguish network-down; a pingable host
    # still classifies as agent_down.
    status, _ = diagnose_unreachable(AGENT_URL, None, _pinger({"192.168.1.50"}))
    assert status == "agent_down"


def test_no_router_configured_and_host_down_is_unreachable():
    status, _ = diagnose_unreachable(AGENT_URL, None, _pinger(set()))
    assert status == "unreachable"
