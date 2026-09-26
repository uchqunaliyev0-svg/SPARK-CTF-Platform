"""Per-player WireGuard configs for the challenge network.

The site only hands out client configs and publishes the peer list; the WireGuard server
pulls that list (see peers_conf) and applies it with `wg syncconf`. Turned on by setting:

  VPN_ENDPOINT           host:port of the WireGuard server, e.g. vpn.sparkctf.uz:51820
  VPN_SERVER_PUBLIC_KEY  the server's public key (base64)
  VPN_SUBNET             player address pool, default 10.13.0.0/16 (server is .1)
  VPN_ALLOWED_IPS        what players route through the tunnel, default 10.13.0.0/16
  VPN_DNS                optional DNS server for the tunnel
  VPN_SYNC_TOKEN         secret the server uses to fetch /vpn/peers.conf

Private keys are generated here, shown to the player once (inside the downloaded file) and
never stored: the database keeps only the public key. Downloading again issues a new key pair.
"""

import base64
import ipaddress
import os
import secrets

# ---------------------------------------------------------------- X25519 (RFC 7748)

_P = 2 ** 255 - 19
_A24 = 121665


def _clamp(k):
    k = bytearray(k)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    return int.from_bytes(k, 'little')


def x25519(scalar, u_bytes):
    """Montgomery ladder, constant structure; returns the 32-byte shared value."""
    k = _clamp(scalar)
    u = int.from_bytes(u_bytes, 'little') & ((1 << 255) - 1)
    x1, x2, z2, x3, z3, swap = u, 1, 0, u, 1, 0
    for t in reversed(range(255)):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = kt
        a, b = (x2 + z2) % _P, (x2 - z2) % _P
        aa, bb = a * a % _P, b * b % _P
        e = (aa - bb) % _P
        c, d = (x3 + z3) % _P, (x3 - z3) % _P
        da, cb = d * a % _P, c * b % _P
        x3, z3 = (da + cb) ** 2 % _P, x1 * (da - cb) ** 2 % _P
        x2, z2 = aa * bb % _P, e * (aa + _A24 * e) % _P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, 'little')


def keypair():
    """(private_b64, public_b64) in WireGuard's format."""
    private = bytearray(secrets.token_bytes(32))
    private[0] &= 248
    private[31] = (private[31] & 127) | 64
    public = x25519(bytes(private), (9).to_bytes(32, 'little'))
    return base64.b64encode(bytes(private)).decode(), base64.b64encode(public).decode()


# ---------------------------------------------------------------- configs

def enabled():
    return bool(os.getenv('VPN_ENDPOINT') and os.getenv('VPN_SERVER_PUBLIC_KEY'))


def _subnet():
    return ipaddress.ip_network(os.getenv('VPN_SUBNET', '10.13.0.0/16'), strict=False)


def address_for(peer_id):
    """Stable tunnel address per peer row; .0 is the network and .1 the server."""
    net = _subnet()
    if peer_id + 1 >= net.num_addresses - 1:
        raise ValueError('VPN address pool exhausted')
    return str(net.network_address + peer_id + 1)


def client_conf(private_key, address):
    dns = os.getenv('VPN_DNS', '').strip()
    lines = [
        '[Interface]',
        f'PrivateKey = {private_key}',
        f'Address = {address}/32',
    ]
    if dns:
        lines.append(f'DNS = {dns}')
    lines += [
        '',
        '[Peer]',
        f"PublicKey = {os.getenv('VPN_SERVER_PUBLIC_KEY')}",
        f"Endpoint = {os.getenv('VPN_ENDPOINT')}",
        f"AllowedIPs = {os.getenv('VPN_ALLOWED_IPS', str(_subnet()))}",
        'PersistentKeepalive = 25',
        '',
    ]
    return '\n'.join(lines)


def peers_conf(peers):
    """[Peer] blocks for the server; peers = iterable of (username, public_key, address)."""
    out = ['# SPARK CTF — generated peer list. Apply with: wg syncconf wg0 <(wg-quick strip wg0)']
    for username, public_key, address in peers:
        out += ['', f'# {username}', '[Peer]', f'PublicKey = {public_key}', f'AllowedIPs = {address}/32']
    return '\n'.join(out) + '\n'
