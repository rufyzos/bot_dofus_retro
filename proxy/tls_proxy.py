"""
Proxy MITM TLS para Dofus Retro 1.48.

Arquitectura:
  1. El archivo hosts redirige dofusretro-co-production.ankama-games.com → 127.0.0.1
  2. El cliente conecta a 127.0.0.1:443 (el puerto lo trae el cliente, no el DNS)
  3. Este proxy termina TLS del cliente usando la CA de mitmproxy
  4. Abre TLS upstream hacia el servidor real de Ankama
  5. Vuelca paquetes Retro (delimitados por \\x00) al log y al Dispatcher

El game server (IP dinámica en AYK) se gestiona abriendo un listener en :5556
y reescribiendo AYK para que el cliente se conecte al proxy local.
"""

import ssl
import socket
import threading
import re
import datetime
import tempfile
import os
from pathlib import Path

from proxy.packet_stream import PacketStream

# ── Configuración ────────────────────────────────────────────────────────────
LOCAL_HOST       = "127.0.0.1"
LOCAL_LOGIN_PORT = 443    # el cliente conecta a :443 — el hosts redirige el hostname aquí
LOCAL_GAME_PORT  = 5556   # game server: AYK se reescribe para apuntar aquí

REAL_LOGIN_HOST  = "dofusretro-co-production.ankama-games.com"
REAL_LOGIN_PORT  = 443

MITMPROXY_CA_PEM = str(Path.home() / ".mitmproxy" / "mitmproxy-ca.pem")

BUFSIZE = 16384
DIRECTION_CLIENT = "C→S"
DIRECTION_SERVER = "S→C"

# ── Generación de certificados de servidor dinámicos ─────────────────────────

def _generate_server_cert(hostname: str, ca_pem_path: str) -> tuple[str, str]:
    """
    Genera un certificado de servidor para `hostname` firmado por la CA de mitmproxy.
    Devuelve (cert_pem_path, key_pem_path) como ficheros temporales.
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime as dt

    # Cargar CA
    ca_pem = Path(ca_pem_path).read_bytes()
    ca_key = serialization.load_pem_private_key(ca_pem, password=None)
    ca_cert = x509.load_pem_x509_certificate(
        b"-----BEGIN CERTIFICATE-----" +
        ca_pem.split(b"-----BEGIN CERTIFICATE-----", 1)[1]
    )

    # Generar clave para el servidor
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Construir certificado
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Escribir a ficheros temporales
    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.close()

    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
    key_file.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    key_file.close()

    return cert_file.name, key_file.name


# Cache de certificados por hostname para no regenerar en cada conexión
_cert_cache: dict[str, tuple[str, str]] = {}
_cert_lock = threading.Lock()


def _get_server_ssl_ctx(hostname: str) -> ssl.SSLContext:
    """Devuelve un SSLContext con cert firmado por la CA de mitmproxy para `hostname`."""
    with _cert_lock:
        if hostname not in _cert_cache:
            _cert_cache[hostname] = _generate_server_cert(hostname, MITMPROXY_CA_PEM)
        cert_path, key_path = _cert_cache[hostname]

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx

# ── Regex AYK ────────────────────────────────────────────────────────────────
_AYK_RE = re.compile(rb"AYK(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+);")

# ── Log ───────────────────────────────────────────────────────────────────────
_LOG_PATH = Path(__file__).parent.parent / "sniffer.log"
_log_lock = threading.Lock()

def _log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with _log_lock:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# ── SSL contexts ──────────────────────────────────────────────────────────────

def _make_client_ssl_ctx() -> ssl.SSLContext:
    """Contexto SSL para conectar upstream (verifica certs reales de Ankama)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_default_certs()
    # No verificar cert upstream en Fase 1 (sniffer pasivo) para simplificar
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Reescritura AYK ──────────────────────────────────────────────────────────

class _GameTarget:
    """Almacena la IP:puerto real del game server interceptado en AYK."""
    host: str | None = None
    port: int | None = None


def _rewrite_ayk(data: bytes, game_target: _GameTarget) -> bytes:
    m = _AYK_RE.search(data)
    if m:
        real_ip   = m.group(1).decode()
        real_port = int(m.group(2).decode())
        game_target.host = real_ip
        game_target.port = real_port
        _log(f"[AYK] Game server real: {real_ip}:{real_port} → redirigiendo a 127.0.0.1:{LOCAL_GAME_PORT}")
        replacement = f"AYK127.0.0.1:{LOCAL_GAME_PORT};".encode()
        data = _AYK_RE.sub(replacement, data, count=1)
    return data


# ── Forwarding ────────────────────────────────────────────────────────────────

def _set_nodelay(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _make_callback(direction: str, on_packet=None):
    def cb(raw: str):
        hdr = raw[:4].rstrip("|") if "|" in raw[:4] else raw[:2]
        rest = raw[len(hdr):]
        if rest.startswith("|"):
            rest = rest[1:]
        fields = rest.split("|") if rest else []
        field_str = " | ".join(f"[{i}]{v}" for i, v in enumerate(fields)) if fields else ""
        _log(f"{direction}  {hdr:<6}  {field_str}")
        if on_packet:
            on_packet(direction, raw)
    return cb


def _forward(src, dst, stream: PacketStream, stop: threading.Event,
             rewrite_fn=None):
    try:
        while not stop.is_set():
            data = src.recv(BUFSIZE)
            if not data:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                break
            if rewrite_fn:
                data = rewrite_fn(data)
            stream.feed(data)
            try:
                dst.sendall(data)
            except OSError:
                break
    except OSError:
        pass
    finally:
        stop.set()


# ── Sesión de proxy ───────────────────────────────────────────────────────────

class TLSProxy:
    def __init__(self, on_packet=None,
                 real_login_host=REAL_LOGIN_HOST,
                 real_login_port=REAL_LOGIN_PORT):
        self._on_packet   = on_packet
        self._real_login  = (real_login_host, real_login_port)
        self._game_target = _GameTarget()
        self._client_ctx  = _make_client_ssl_ctx()
        self._login_srv   = None
        self._game_srv    = None

    def _handle_login(self, raw_client: socket.socket, addr):
        _log(f"[LOGIN] Cliente conectado: {addr}")
        _set_nodelay(raw_client)

        # Terminar TLS del cliente con cert firmado para el hostname de Ankama
        try:
            server_ctx = _get_server_ssl_ctx(self._real_login[0])
            raw_client.settimeout(15)
            client = server_ctx.wrap_socket(raw_client, server_side=True)
            raw_client.settimeout(None)
            _log(f"[LOGIN] TLS OK — cipher={client.cipher()}, peer={client.getpeercert(binary_form=False)}")
        except ssl.SSLError as e:
            _log(f"[LOGIN] TLS handshake fallido: {e}")
            raw_client.close()
            return
        except TimeoutError:
            _log(f"[LOGIN] TLS handshake timeout — el cliente no envió ClientHello en 15s")
            raw_client.close()
            return

        # Abrir TLS upstream hacia Ankama
        try:
            raw_up = socket.create_connection(self._real_login)
            _set_nodelay(raw_up)
            server = self._client_ctx.wrap_socket(
                raw_up, server_hostname=self._real_login[0]
            )
        except (OSError, ssl.SSLError) as e:
            _log(f"[LOGIN] Conexión upstream fallida: {e}")
            client.close()
            return

        stop = threading.Event()
        s2c_stream = PacketStream(_make_callback(DIRECTION_SERVER, self._on_packet))
        c2s_stream = PacketStream(_make_callback(DIRECTION_CLIENT, self._on_packet))

        t1 = threading.Thread(
            target=_forward,
            args=(server, client, s2c_stream, stop),
            kwargs={"rewrite_fn": lambda d: _rewrite_ayk(d, self._game_target)},
            daemon=True,
        )
        t2 = threading.Thread(
            target=_forward,
            args=(client, server, c2s_stream, stop),
            daemon=True,
        )
        t1.start(); t2.start()
        stop.wait()
        try: client.close()
        except: pass
        try: server.close()
        except: pass
        _log(f"[LOGIN] Sesión cerrada: {addr}")

    def _handle_game(self, raw_client: socket.socket, addr):
        if not self._game_target.host:
            _log("[GAME] Game server desconocido (AYK aún no interceptado)")
            raw_client.close()
            return

        _log(f"[GAME] Cliente conectado: {addr} → {self._game_target.host}:{self._game_target.port}")
        _set_nodelay(raw_client)

        try:
            server_ctx = _get_server_ssl_ctx(self._game_target.host)
            client = server_ctx.wrap_socket(raw_client, server_side=True)
        except ssl.SSLError as e:
            _log(f"[GAME] TLS handshake con cliente fallido: {e}")
            raw_client.close()
            return

        try:
            raw_up = socket.create_connection((self._game_target.host, self._game_target.port))
            _set_nodelay(raw_up)
            server = self._client_ctx.wrap_socket(
                raw_up, server_hostname=self._game_target.host
            )
        except (OSError, ssl.SSLError) as e:
            _log(f"[GAME] Conexión upstream fallida: {e}")
            client.close()
            return

        stop = threading.Event()
        s2c_stream = PacketStream(_make_callback(DIRECTION_SERVER, self._on_packet))
        c2s_stream = PacketStream(_make_callback(DIRECTION_CLIENT, self._on_packet))

        t1 = threading.Thread(
            target=_forward, args=(server, client, s2c_stream, stop), daemon=True
        )
        t2 = threading.Thread(
            target=_forward, args=(client, server, c2s_stream, stop), daemon=True
        )
        t1.start(); t2.start()
        stop.wait()
        try: client.close()
        except: pass
        try: server.close()
        except: pass
        _log(f"[GAME] Sesión cerrada: {addr}")

    def _accept_loop(self, srv: socket.socket, handler):
        while True:
            try:
                client, addr = srv.accept()
                threading.Thread(target=handler, args=(client, addr), daemon=True).start()
            except OSError:
                break

    def start(self):
        self._login_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._login_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._login_srv.bind((LOCAL_HOST, LOCAL_LOGIN_PORT))
        self._login_srv.listen(5)
        _log(f"[Proxy] Login TLS en {LOCAL_HOST}:{LOCAL_LOGIN_PORT}")

        self._game_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._game_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._game_srv.bind((LOCAL_HOST, LOCAL_GAME_PORT))
        self._game_srv.listen(5)
        _log(f"[Proxy] Game  TLS en {LOCAL_HOST}:{LOCAL_GAME_PORT}")

        threading.Thread(
            target=self._accept_loop, args=(self._login_srv, self._handle_login), daemon=True
        ).start()
        threading.Thread(
            target=self._accept_loop, args=(self._game_srv, self._handle_game), daemon=True
        ).start()

    def stop(self):
        if self._login_srv:
            try: self._login_srv.close()
            except: pass
        if self._game_srv:
            try: self._game_srv.close()
            except: pass
