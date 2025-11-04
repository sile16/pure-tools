#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# scan_nfs_fsid.py <ip>
#
# Python 2.7.5-compatible. No third-party modules.
# Does raw ONC-RPC over UDP to list exports (mountd v3), mount each,
# then calls NFSv3 GETATTR to read the FSID and prints it.
#
# Notes:
# - Requires that the server's mountd allows MNT from your host.
# - Works best when server supports NFSv3.
# - Uses AUTH_NULL by default; many servers accept that for EXPORTS/MNT/GETATTR.
#
import sys
import socket
import struct
import random
import time

PMAP_PROG   = 100000
PMAP_VERS   = 2
PMAP_GETPORT= 3

MNT_PROG    = 100005
MNT_VERS3   = 3
MNT_PROC_MNT= 1
MNT_PROC_EXPORT=5
MNT3_OK     = 0

NFS_PROG    = 100003
NFS_VERS3   = 3
NFS3_GETATTR= 1
NFS3_OK     = 0

IPPROTO_UDP = 17

RPC_CALL    = 0
RPC_REPLY   = 1
RPC_VERS    = 2

AUTH_NULL   = 0
AUTH_UNIX   = 1
MSG_ACCEPTED= 0
SUCCESS     = 0

def be32(x): return struct.pack(">I", x & 0xffffffff)
def be32u(data, off):
    return struct.unpack(">I", data[off:off+4])[0], off+4

def be64u_from_two32(hi, lo):
    return (hi << 32) | lo

def xdr_pad_len(n):
    return ((n + 3) // 4) * 4

def xdr_string(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    ln = len(s)
    pad = xdr_pad_len(ln) - ln
    return be32(ln) + s + ("\x00" * pad)

def xdr_opaque(buf):
    ln = len(buf)
    pad = xdr_pad_len(ln) - ln
    return be32(ln) + buf + ("\x00" * pad)

def xdr_auth_null():
    # opaque_auth { flavor, length, body[] }
    return be32(AUTH_NULL) + be32(0)

def rpc_call_msg(xid, prog, vers, proc, cred=None, verf=None, body=""):
    if cred is None: cred = xdr_auth_null()
    if verf is None: verf = xdr_auth_null()
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
    xid, off        = be32u(buf, off)
    mtype, off      = be32u(buf, off)
    if mtype != RPC_REPLY:
        raise ValueError("not a REPLY")
    stat, off       = be32u(buf, off)  # MSG_ACCEPTED or DENIED
    if stat != MSG_ACCEPTED:
        raise ValueError("RPC denied (stat=%d)" % stat)
    # verifier opaque_auth
    flav, off       = be32u(buf, off)
    vlen, off       = be32u(buf, off)
    off += xdr_pad_len(vlen)
    accept_stat, off= be32u(buf, off)
    if accept_stat != SUCCESS:
        raise ValueError("RPC accepted but not SUCCESS (stat=%d)" % accept_stat)
    # remaining is procedure result
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

def pmap_getport(host, prog, vers, proto=IPPROTO_UDP):
    xid = random.randint(1, 0x7fffffff)
    # mapping: program, version, protocol, port
    body = be32(prog) + be32(vers) + be32(proto) + be32(0)
    req  = rpc_call_msg(xid, PMAP_PROG, PMAP_VERS, PMAP_GETPORT, body=body)
    resp = udp_call(host, 111, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    port, _ = be32u(rest, 0)
    return port

def mnt_export_list(host, mnt_port):
    """
    MOUNTPROC_EXPORT (v3) returns a linked list:
      exportlist -> [ dirpath(string), groups(list), next(ptr) ]
    groups -> [ name(string), next(ptr) ]
    Return: list of dirpath strings.
    """
    xid  = random.randint(1, 0x7fffffff)
    req  = rpc_call_msg(xid, MNT_PROG, MNT_VERS3, MNT_PROC_EXPORT, body="")
    resp = udp_call(host, mnt_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    exports = []
    off = 0
    # The list is encoded as: bool(has_entry) then entry; repeated. bool is 0/1 (uint32)
    while True:
        if off + 4 > len(rest):
            break
        has, off = be32u(rest, off)
        if has == 0:
            break
        # dirpath (string)
        # string: len(4) + data + pad
        if off + 4 > len(rest): break
        slen, off = be32u(rest, off)
        end = off + xdr_pad_len(slen)
        dirpath = rest[off: off + slen]
        off = end
        exports.append(dirpath)
        # groups list: skip it
        # groups is a linked list: bool(has) -> name(string) -> next...
        while True:
            if off + 4 > len(rest): break
            ghas, off = be32u(rest, off)
            if ghas == 0:
                break
            # name
            if off + 4 > len(rest): break
            glen, off = be32u(rest, off)
            off += xdr_pad_len(glen)
        # next (handled by outer loop via 'has')
    return exports

def mnt_mnt(host, mnt_port, dirpath):
    """
    MOUNTPROC_MNT (v3)
    Arg: dirpath (string)
    Res: mountres3 {
         fhs_status (u32)
         if OK: fhandle3 { len(u32) data[] pad } and authflavors[]
    }
    Return (status, fh_bytes) where fh_bytes may be None on error.
    """
    xid  = random.randint(1, 0x7fffffff)
    arg  = xdr_string(dirpath)
    req  = rpc_call_msg(xid, MNT_PROG, MNT_VERS3, MNT_PROC_MNT, body=arg)
    resp = udp_call(host, mnt_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    off = 0
    status, off = be32u(rest, off)
    if status != MNT3_OK:
        return status, None
    # fhandle3
    fh_len, off = be32u(rest, off)
    pad = xdr_pad_len(fh_len) - fh_len
    fh   = rest[off: off + fh_len]
    off += fh_len + pad
    # auth flavors array: length + entries (we don't need them)
    if off + 4 <= len(rest):
        n, off = be32u(rest, off)
        off += 4 * n
    return status, fh

def nfs3_getattr(host, nfs_port, fh):
    """
    NFSv3 GETATTR
    Arg: nfs_fh3 (len + opaque)
    Res: status (u32); if OK:
         post_op_attr = attributes_follow(bool)
         fattr3:
           type(4) mode(4) nlink(4) uid(4) gid(4)
           size(8) used(8)
           rdev: specdata3 { specdata1(u32) specdata2(u32) }
           fsid(8) fileid(8)
           atime(3*4) mtime(3*4) ctime(3*4)
    Return: (status, fsid_uint64)  when OK; else (status, None)
    """
    xid = random.randint(1, 0x7fffffff)
    arg = xdr_opaque(fh)
    req = rpc_call_msg(xid, NFS_PROG, NFS_VERS3, NFS3_GETATTR, body=arg)
    resp= udp_call(host, nfs_port, req)
    rxid, rest = rpc_parse_reply(resp)
    if rxid != xid: raise ValueError("XID mismatch")
    off = 0
    status, off = be32u(rest, off)
    if status != NFS3_OK:
        return status, None
    # attributes_follow (bool)
    attr_follow, off = be32u(rest, off)
    if attr_follow == 0:
        return status, None
    # Skip fields up to fsid:
    # 5 * u32
    off += 4 * 5
    # size(8) used(8) => two u32 each
    off += 8  # size (2 * 4)
    off += 8  # used (2 * 4)
    # rdev: two u32
    off += 8
    # fsid: uint64 (two u32)
    hi, off = be32u(rest, off)
    lo, off = be32u(rest, off)
    fsid = be64u_from_two32(hi, lo)
    return status, fsid

def main():
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: %s <ip>\n" % sys.argv[0])
        sys.exit(1)
    host = sys.argv[1]

    # 1) Discover ports
    try:
        mnt_port = pmap_getport(host, MNT_PROG, MNT_VERS3, IPPROTO_UDP)
        nfs_port = pmap_getport(host, NFS_PROG, NFS_VERS3, IPPROTO_UDP)
    except Exception as e:
        sys.stderr.write("portmap/GETPORT failed: %s\n" % (e,))
        sys.exit(2)
    if mnt_port == 0:
        sys.stderr.write("mountd v3 not available on %s\n" % host); sys.exit(3)
    if nfs_port == 0:
        sys.stderr.write("nfs v3 not available on %s\n" % host); sys.exit(4)

    # 2) List exports
    try:
        exports = mnt_export_list(host, mnt_port)
    except Exception as e:
        sys.stderr.write("MOUNTPROC_EXPORT failed: %s\n" % (e,))
        sys.exit(5)

    if not exports:
        sys.stderr.write("No exports returned by server.\n")
        sys.exit(6)

    # 3) For each export, MNT then GETATTR to read fsid
    for dp in exports:
        dp_print = dp
        try:
            status, fh = mnt_mnt(host, mnt_port, dp)
            if status != MNT3_OK or fh is None:
                print("%s\tstatus=%d (mount failed)" % (dp_print, status))
                continue
            st, fsid = nfs3_getattr(host, nfs_port, fh)
            if st == NFS3_OK and fsid is not None:
                # print fsid as hex/decimal
                print("%s\tfsid=0x%x (%d)" % (dp_print, fsid, fsid))
            else:
                print("%s\tgetattr status=%d (no fsid)" % (dp_print, st))
        except socket.timeout:
            print("%s\t(timeout)" % dp_print)
        except Exception as e:
            print("%s\t(error: %s)" % (dp_print, e))

if __name__ == "__main__":
    # seed XIDs differently each run
    random.seed(int(time.time()) ^ (os.getpid() if 'os' in globals() else 0))
    # Avoid importing os earlier to keep dependencies minimal in old pythons
    try:
        import os
    except:
        pass
    main()
