"""
Minimal SSL stub for PyInstaller builds without OpenSSL.

Provides the subset of ssl module interfaces that asyncio and websockets
require at import time. All TLS operations raise SSLError at runtime.
"""


class SSLError(OSError):
    pass


class SSLWantReadError(SSLError):
    pass


class SSLWantWriteError(SSLError):
    pass


class SSLSyscallError(SSLError):
    pass


class SSLEOFError(SSLError):
    pass


class SSLZeroReturnError(SSLError):
    pass


class CertificateError(Exception):
    pass


class MemoryBIO:
    """Dummy MemoryBIO for asyncio compatibility."""

    def __init__(self):
        self._buffer = b""

    def read(self, n=-1):
        if n < 0 or n >= len(self._buffer):
            result = self._buffer
            self._buffer = b""
            return result
        result = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return result

    def write(self, data):
        self._buffer += data
        return len(data)

    def pending(self):
        return len(self._buffer)

    def eof(self):
        return not self._buffer


class SSLSocket:
    family = 0
    type = 0
    proto = 0

    def __init__(self, *args, **kwargs):
        pass


class SSLContext:
    protocol = None
    options = 0
    verify_flags = 0
    verify_mode = 0
    check_hostname = False
    maximum_version = None
    minimum_version = None

    def __init__(self, protocol=None):
        self.protocol = protocol

    def load_cert_chain(self, certfile, keyfile=None, password=None):
        raise SSLError("SSL not available in this build")

    def load_verify_locations(self, cafile=None, capath=None, cadata=None):
        raise SSLError("SSL not available in this build")

    def set_default_verify_paths(self):
        raise SSLError("SSL not available in this build")

    def wrap_socket(self, sock, *args, **kwargs):
        raise SSLError("SSL not available in this build")

    def wrap_bio(self, incoming, outgoing, server_side=False, server_hostname=None):
        raise SSLError("SSL not available in this build")


# Constants
CERT_NONE = 0
CERT_OPTIONAL = 1
CERT_REQUIRED = 2

VERIFY_DEFAULT = 0
VERIFY_CRL_CHECK_LEAF = 0
VERIFY_CRL_CHECK_CHAIN = 0
VERIFY_X509_STRICT = 0
VERIFY_X509_TRUSTED_FIRST = 0

OP_ALL = 0
OP_NO_SSLv2 = 0
OP_NO_SSLv3 = 0
OP_NO_TLSv1 = 0
OP_NO_TLSv1_1 = 0
OP_NO_TLSv1_2 = 0
OP_NO_TLSv1_3 = 0
OP_NO_COMPRESSION = 0
OP_SINGLE_DH_USE = 0
OP_SINGLE_ECDH_USE = 0
OP_ENABLE_MIDDLEBOX_COMPAT = 0
OP_NO_RENEGOTIATION = 0

HAS_SNI = True
HAS_ALPN = True
HAS_ECDH = True
HAS_NPN = False
HAS_PHA = True

OPENSSL_VERSION = "OpenSSL stub"
OPENSSL_VERSION_NUMBER = 0x00000000
OPENSSL_VERSION_INFO = (0, 0, 0, 0, 0)


# Functions
def create_default_context(*args, **kwargs):
    return SSLContext()


def wrap_socket(sock, *args, **kwargs):
    raise SSLError("SSL not available in this build")


def get_server_certificate(addr, ssl_version=0, ca_certs=None):
    raise SSLError("SSL not available in this build")


def RAND_bytes(n):
    import os
    return os.urandom(n)


def RAND_pseudo_bytes(n):
    return RAND_bytes(n), True


def RAND_status():
    return True


def RAND_add(s, entropy):
    pass
