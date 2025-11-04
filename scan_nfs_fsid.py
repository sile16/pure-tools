#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# scan_nfs_fsid.py <ip> [uid gid hostname]
# Python 2.7.5, no external modules.
#
# - Portmap GETPORT (UDP) to discover mountd v3 and nfs v3 ports
# - MOUNTPROC_EXPORT (v3) over UDP to get export list
# - MOUNTPROC_MNT (v3) over UDP to get file handle
# - NFSv3 GETATTR over **TCP** with **AUTH_SYS** to read FSID
#
import sys, socket, struct, random, time

PMAP_PROG, PMAP_VERS, PMAP_GETPORT = 100000, 2, 3
MNT_PROG, MNT_VERS3 = 100005, 3
MNT_PROC_MNT, MNT_PROC_EXPORT = 1, 5
MNT3_OK = 0

NFS_PROG, NFS_VERS3 = 100003, 3
NFS3_GETATTR, NFS3_OK = 1, 0

IPPROTO_UDP = 17

RPC_CALL, RPC_REPLY, RPC_VERS = 0, 1, 2
AUTH_NULL, AUTH_UNIX = 0, 1
MSG_ACCEPTED, SUCCESS = 0, 0

def be32(x): return struct.pack(">I", x & 0xffffffff)
def be32u(buf, off): return struct.unpack(">I", buf[off:off+4])[0], off+4
def xdr_pad_len(n): return ((n + 3) // 4) * 4

def xdr_bytes(b):
    ln = len(b)
    pad = xdr_pad_len(ln) - ln
    return be32(ln) + b + ("\x00" * pad)

def xdr_string(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    return xdr_bytes(s)

def xdr_auth_null():
    # opaque_auth { flavor(u32), length(u32), body[] }
    return be32(AUTH_NULL) + be32(0)

def xdr_auth_sys(uid, gid, hostname, auxgids=None):
    if auxgids is None:
        auxgids = []
    if isinstance(hostname, unicode):
        hostname = hostname.encode("utf-8")
    # AUTH_UNIX fields:
    # stamp(u32), machinename(string), uid(u32), gid(u32), len(u32), gids[len](u32)
    stamp = 0
    body = []
    body.append(be32(stamp))
    body.append(xdr_string(hostname))
    body.append(be32(uid))
    body.append(be32(gid))
    body.append(be32(len(auxgids)))
    for g in auxgids:
        body.append(be32(g))
    body = "".join(body)
    return be32(AUTH_UNIX) + be32(len(body)) + body + ("\x00" * (xdr_pad_len(len(body)) - len(body)))

def rpc_call_msg(xid, prog, vers, proc, cred, verf, body):
    # rpc_msg (CALL)
    out = []
    out.append(be32(xid))
    out.append(be32(RPC_CALL))
    out.append(be32(RPC_VERS))
    out.append(be32(prog))
    out.append(be32(vers))
    out.append(be32(proc))
    out.append(cred)
    out.append(verf)
    out.append(body)
    return "".join(out)

def rpc_parse_reply(buf):
    off = 0
    xid, off = be32u(buf, off)
    mtype, off = be32u(buf, off)
    if mtype != RPC_REPLY:
        raise ValueError("not an RPC REPLY")
    stat, off = be32u(buf, off)  # accepted/denied
    if stat != MSG_ACCEPTED:
        raise ValueError("RPC denied (stat=%d)" % stat)
    # verifier opaque_auth
    flav, off = be32u(buf, off)
    vlen, off = be32u(buf, off)
    off += xdr_pad_len(vlen)
    accept_stat, off = be32u(buf, off)
    if accept_stat != SUCCESS:
        raise ValueError("RPC accepted but non-success (stat=%d)" % accept_stat)
    return xid, buf[off:]

def udp_call(host, port, payload, timeout=2.0, retries=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    last_err = None
    for _ in range(retries):
        try:
            s.sendto(payload, (host, port))
            data, _ = s.recvfrom(65535)
            s.close()
            return data
        except Exception as e:
            last_err = e
    s.close()
    raise last_err

def tcp_call(host, port, payload, timeout=3.0):
    # RPC over TCP uses Record Marking: 4 bytes header:
    # bit31=1 last fragment, bits0-30 = length
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    rm = struct.pack(">I", 0x80000000 | len(payload))
    s.sendall(rm + payload)
    # Read fragments until last-frag seen
    chunks = []
    total = 0
    while True:
        hdr = _recv_exact(s, 4)
        if not hdr:
            break
        (frag,) = struct.unpack(">I", hdr)
        last = (frag & 0x80000000) != 0
        flen = frag & 0x7fffffff
        data = _recv_exact(s, flen)
        chunks.append(data)
        total += len(data)
        if last:
            break
    s.close()
    return "".join(chunks)

def _recv_exact(sock, n):
    buf = []
    r = 0
    while r < n:
        chunk = sock.recv(n - r)
        if not chunk:
            break
        buf.append(chunk)
        r += len(chunk)
    return "".join(buf)

def pmap_getport(host, prog, vers, proto=IPPROTO_UDP):
    xid = random.randint(1, 0x7fffffff)
    body = be32(prog) + be32(vers) + be32(proto) + be32(0)
    req  = rpc_call_msg(xid, PMAP_PROG, PMAP_VERS, PMAP_GETPORT, xdr_auth_null(), xdr_auth_null(), body)
    resp = udp_call(host, 111, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    port, _ = be32u(rest, 0)
    return port

def mnt_export_list(host, mnt_port):
    xid  = random.randint(1, 0x7fffffff)
    req  = rpc_call_msg(xid, MNT_PROG, MNT_VERS3, MNT_PROC_EXPORT, xdr_auth_null(), xdr_auth_null(), "")
    resp = udp_call(host, mnt_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    exports = []
    off = 0
    while True:
        if off + 4 > len(rest): break
        has, off = be32u(rest, off)
        if has == 0: break
        slen, off = be32u(rest, off)
        end = off + xdr_pad_len(slen)
        dirpath = rest[off: off + slen]
        off = end
        exports.append(dirpath)
        # skip groups list
        while True:
            if off + 4 > len(rest): break
            ghas, off = be32u(rest, off)
            if ghas == 0: break
            glen, off = be32u(rest, off)
            off += xdr_pad_len(glen)
    return exports

def mnt_mnt(host, mnt_port, dirpath):
    xid  = random.randint(1, 0x7fffffff)
    arg  = xdr_string(dirpath)
    req  = rpc_call_msg(xid, MNT_PROG, MNT_VERS3, MNT_PROC_MNT, xdr_auth_null(), xdr_auth_null(), arg)
    resp = udp_call(host, mnt_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    off = 0
    status, off = be32u(rest, off)
    if status != MNT3_OK:
        return status, None
    fh_len, off = be32u(rest, off)
    pad = xdr_pad_len(fh_len) - fh_len
    fh   = rest[off: off + fh_len]
    off += fh_len + pad
    # skip auth flavors
    if off + 4 <= len(rest):
        n, off = be32u(rest, off)
        off += 4 * n
    return status, fh

def nfs3_getattr_tcp_authsys(host, nfs_port, fh, uid, gid, hostname):
    xid = random.randint(1, 0x7fffffff)
    cred = xdr_auth_sys(uid, gid, hostname, [])
    verf = xdr_auth_null()
    arg  = xdr_bytes(fh)  # nfs_fh3 = opaque<> (len + bytes + pad)
    req  = rpc_call_msg(xid, NFS_PROG, NFS_VERS3, NFS3_GETATTR, cred, verf, arg)
    resp = tcp_call(host, nfs_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch in NFS reply")
    off = 0
    status, off = be32u(rest, off)
    if status != NFS3_OK:
        return status, None
    # GETATTR3resok -> fattr3 directly (no boolean here)
    # fattr3 layout (RFC 1813):
    # type, mode, nlink, uid, gid (5 * u32)
    off += 4 * 5
    # size(8) used(8)
    off += 8
    off += 8
    # rdev specdata1/specdata2 (2 * u32)
    off += 8
    # fsid (uint64 as two u32)
    hi, off = be32u(rest, off)
    lo, off = be32u(rest, off)
    fsid = (hi << 32) | lo
    return status, fsid

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: %s <ip> [uid gid hostname]\n" % sys.argv[0]); sys.exit(1)
    host = sys.argv[1]
    uid = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    gid = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    hostname = sys.argv[4] if len(sys.argv) > 4 else "client"

    random.seed(int(time.time()) & 0x7fffffff)

    # Discover ports
    try:
        mnt_port = pmap_getport(host, MNT_PROG, MNT_VERS3, IPPROTO_UDP)
        nfs_port_udp = pmap_getport(host, NFS_PROG, NFS_VERS3, IPPROTO_UDP)
        nfs_port_tcp = pmap_getport(host, NFS_PROG, NFS_VERS3, 6)  # TCP protocol number
    except Exception as e:
        sys.stderr.write("portmap GETPORT failed: %s\n" % (e,)); sys.exit(2)

    if mnt_port == 0:
        sys.stderr.write("mountd v3 not available on %s\n" % host); sys.exit(3)
    if nfs_port_tcp == 0 and nfs_port_udp == 0:
        sys.stderr.write("nfs v3 not available on %s\n" % host); sys.exit(4)

    # List exports
    try:
        exports = mnt_export_list(host, mnt_port)
    except Exception as e:
        sys.stderr.write("EXPORTS failed: %s\n" % (e,)); sys.exit(5)

    if not exports:
        sys.stderr.write("No exports returned by server.\n"); sys.exit(6)

    # Prefer TCP for NFS calls
    nfs_port = nfs_port_tcp if nfs_port_tcp != 0 else nfs_port_udp

    # For each export: mount -> getattr over TCP/AUTH_SYS
    for dp in exports:
        path = dp
        try:
            st, fh = mnt_mnt(host, mnt_port, path)
            if st != MNT3_OK or fh is None:
                print("%s\tmount status=%d" % (path, st)); continue
            st2, fsid = nfs3_getattr_tcp_authsys(host, nfs_port, fh, uid, gid, hostname)
            if st2 == NFS3_OK and fsid is not None:
                print("%s\tfsid=0x%x (%d)" % (path, fsid, fsid))
            else:
                print("%s\tgetattr status=%d (no fsid)" % (path, st2))
        except socket.timeout:
            print("%s\t(timeout)" % path)
        except Exception as e:
            print("%s\t(error: %s)" % (path, e))

if __name__ == "__main__":
    main()
