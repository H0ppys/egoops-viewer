"""服务器用的是自签证书，客户端固定校验这张证书（不信任其它任何 CA）。"""
import os
import ssl
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.path.join(getattr(sys, "_MEIPASS", HERE), "egoops.crt"),
    os.path.join(HERE, "egoops.crt"),
]

_CTX = None


def context():
    global _CTX
    if _CTX is not None:
        return _CTX
    for p in CANDIDATES:
        if os.path.exists(p):
            _CTX = ssl.create_default_context(cafile=p)
            return _CTX
    _CTX = ssl.create_default_context()
    return _CTX


def urlopen(req, timeout=30):
    return urllib.request.urlopen(req, timeout=timeout, context=context())
