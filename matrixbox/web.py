import io
import re
import sys
import time
from errno import EAGAIN, ECONNRESET

_VARIABLE_RE = re.compile("^<([a-zA-Z]+)>$")


class Request:
    def __init__(self, method, full_path):
        self.method = method
        self.path = full_path.split("?")[0]
        self.params = self._parse_params(full_path)
        self.headers = {}
        self.body = None

    @staticmethod
    def _parse_params(path):
        query_string = path.split("?")[1] if "?" in path else ""
        params = {}
        for pair in query_string.split("&"):
            key_val = pair.split("=")
            if len(key_val) == 2:
                params[key_val[0]] = key_val[1]

        return params


def url_decode(value: str) -> str:
    value = value.replace("+", " ")
    if "%" not in value:
        return value

    parts = value.split("%")
    result = [parts[0]]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                result.append(chr(int(part[:2], 16)) + part[2:])
                continue
            except ValueError:
                pass

        result.append("%" + part)

    return "".join(result)


class Router:
    _BUFFER_SIZE = 1024 * 8

    def __init__(self):
        self.routes = []
        self._recv_buffer = bytearray(self._BUFFER_SIZE)

    def route(self, rule, method="GET"):
        def decorator(handler):
            self._add_route(method, rule, handler)

            return handler

        return decorator

    def clear(self):
        self.routes.clear()

    def _add_route(self, method, rule, handler):
        regex = "^"
        for part in rule.split("/"):
            if _VARIABLE_RE.match(part):
                regex += r"([a-zA-Z0-9_-]+)\/"
            else:
                regex += part + r"\/"

        regex += "?$"
        self.routes.append((re.compile(regex), method, handler))

    def _match(self, path, method):
        for matcher, route_method, handler in self.routes:
            match = matcher.match(path)
            if match and method == route_method:
                return match.groups(), handler

        return None

    def listen(self, sock):
        try:
            client, _ = sock.accept()
        except OSError as e:
            if e.errno in (EAGAIN, ECONNRESET):
                return

            raise

        try:
            request = self._read_request(client)
            if request is None:
                return

            match = self._match(request.path, request.method)
            if match:
                args, handler = match
                status, headers, body = handler(request, *args)
                self._send_response(client, status, headers, body)
            else:
                self._send_response(client, 404, {}, "Not found")
        except BaseException as e:
            # Last line of defense for one request — must never itself raise (see docs/architecture.md).
            try:
                sys.print_exception(e)
            except Exception:
                print(f"Error with request: {type(e).__name__}: {e}")

            try:
                self._send_response(client, 500, {}, "Error")
            except OSError:
                pass
        finally:
            client.close()

    def _read_request(self, client):
        message = bytearray()
        hdr_end = -1
        content_length = 0
        last_data = time.monotonic()

        while time.monotonic() - last_data < 2.0:
            try:
                num_received = client.recv_into(self._recv_buffer)
                if num_received == 0:
                    break

                for i in range(num_received):
                    if self._recv_buffer[i] == 0x00:
                        num_received = i
                        break

                if num_received > 0:
                    message.extend(self._recv_buffer[:num_received])
                    last_data = time.monotonic()

                if hdr_end < 0:
                    hdr_end = message.find(b"\r\n\r\n")
                    if hdr_end >= 0:
                        for line in str(message[:hdr_end], "utf-8").split("\r\n"):
                            if line.lower().startswith("content-length:"):
                                content_length = int(line.split(":", 1)[1].strip())
                                break

                if hdr_end >= 0 and len(message) - (hdr_end + 4) >= content_length:
                    break
            except OSError as error:
                if error.errno == EAGAIN:
                    time.sleep(0.01)
                    continue

                break

        if not message:
            return None

        reader = io.BytesIO(message)
        line = str(reader.readline(), "utf-8")
        parts = line.rstrip("\r\n").split(None, 2)
        if len(parts) < 3:
            return None

        method, full_path, _ = parts

        request = Request(method, full_path)
        request.headers = self._parse_headers(reader)
        request.body = self._parse_body(reader, request.headers)

        return request

    @staticmethod
    def _parse_headers(reader):
        headers = {}
        for line in reader:
            if line == b"\r\n":
                break

            title, content = str(line, "utf-8").split(":", 1)
            headers[title.strip().lower()] = content.strip()

        return headers

    @staticmethod
    def _parse_body(reader, headers):
        content_length = int(headers.get("content-length", 0))
        data = reader.read(content_length) if content_length > 0 else reader.read()

        return str(data, "utf-8") if data else ""

    @staticmethod
    def _send_response(client, code, headers, data):
        headers = dict(headers)
        headers["Access-Control-Allow-Origin"] = "*"
        headers.setdefault("Content-Type", "text/html; charset=utf-8")
        headers["Server"] = "MatrixBOX/2.0 (CircuitPython)"
        headers["Connection"] = "close"
        if isinstance(data, str):
            data = data.encode("utf-8")

        headers["Content-Length"] = len(data)

        parts = [f"HTTP/1.0 {code} OK\r\n".encode()]
        for key, value in headers.items():
            parts.append(f"{key}: {value}\r\n".encode())

        parts.append(b"\r\n")
        parts.append(data)
        response = b"".join(parts)

        sent_total = 0
        while sent_total < len(response):
            try:
                sent_total += client.send(response[sent_total:])
            except OSError as e:
                # ESP32-S2 EAGAIN quirk — see adafruit/circuitpython#4420.
                if e.errno == EAGAIN:
                    time.sleep(0.1)
                    continue

                return sent_total

        return sent_total


# The one route table for the whole device — see docs/architecture.md.
router = Router()
