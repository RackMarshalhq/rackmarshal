#!/usr/bin/env python3
"""Print an nftables rule file that limits the RackMarshal status page to known callers.

Optional. The status page listens on 127.0.0.1 by default and then needs no rule.
If you set STATUS_API_LISTEN_ADDRESS to a network address, run this to list who may
connect. It only prints; it changes nothing. See CONFIGURATION.md.

  python3 status-acl.py --allow 192.168.1.10 --allow 192.168.1.0/28 > status-acl.nft
"""
import argparse
import ipaddress
import sys

TABLE = "rm_status_acl"


def parse_sources(values):
    v4, v6 = [], []
    for raw in values:
        text = raw.strip()
        if not text or any(ch in text for ch in " ,;{}\n\t\"'"):
            raise ValueError("invalid address: %r" % raw)
        try:
            network = ipaddress.ip_network(text, strict=True)
        except ValueError:
            raise ValueError("invalid address or network: %r" % raw) from None
        if network.num_addresses > 1 and network.prefixlen == 0:
            raise ValueError("refusing 0.0.0.0/0 or ::/0: that allows everyone")
        (v4 if network.version == 4 else v6).append(str(network if network.num_addresses > 1 else network.network_address))
    if not v4 and not v6:
        raise ValueError("give at least one --allow address")
    return sorted(set(v4)), sorted(set(v6))


def render(port, values):
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("port must be 1-65535")
    v4, v6 = parse_sources(values)
    lines = [
        "# RackMarshal status page (port %d): only listed callers may connect." % port,
        "# Loopback is always allowed. Traffic to other ports is not touched.",
        "table inet %s {" % TABLE,
        "    chain input {",
        "        type filter hook input priority -5; policy accept;",
        '        iifname "lo" accept',
    ]
    if v4:
        lines.append("        tcp dport %d ip saddr { %s } accept" % (port, ", ".join(v4)))
    if v6:
        lines.append("        tcp dport %d ip6 saddr { %s } accept" % (port, ", ".join(v6)))
    lines += ["        tcp dport %d counter drop" % port, "    }", "}", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=9110)
    p.add_argument("--allow", action="append", required=True, metavar="ADDRESS_OR_NETWORK")
    a = p.parse_args()
    try:
        sys.stdout.write(render(a.port, a.allow))
    except ValueError as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
