# Install:
#   sudo cp garni_http.py /etc/weewx/bin/user/
# weewx.conf:
#   [Station]
#       station_type = GarniHTTP
#
#   [GarniHTTP]
#       driver = user.garni_http
#       host = 0.0.0.0
#       port = 8080
#       path = /
#       stale_timeout = 900
#       queue_size = 300
#
# Restart:
#   sudo systemctl restart weewx
#   sudo journalctl -u weewx -f
import json
import logging
import queue
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import weewx
import weewx.drivers


DRIVER_NAME = "GarniHTTP"
DRIVER_VERSION = "0.2"

log = logging.getLogger(__name__)

def loader(config_dict, engine):
    return GarniHTTPDriver(**config_dict[DRIVER_NAME])


class GarniHTTPDriver(weewx.drivers.AbstractDevice):
    def __init__(self, **stn_dict):
        self.host = stn_dict.get("host", "0.0.0.0")
        self.port = int(stn_dict.get("port", 8080))
        self.path = stn_dict.get("path", "/")
        self.stale_timeout = int(stn_dict.get("stale_timeout", 900))
        self.queue_size = int(stn_dict.get("queue_size", 300))

        self.packet_queue = queue.Queue(maxsize=self.queue_size)
        self.last_rain_day = None
        self.last_packet_ts = None

        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer((self.host, self.port), handler)

        self.thread = threading.Thread(target=self.httpd.serve_forever, name="GarniHTTPServer")
        self.thread.daemon = True
        self.thread.start()

        log.info("%s driver version %s listening on %s:%s", DRIVER_NAME, DRIVER_VERSION, self.host, self.port)

    @property
    def hardware_name(self):
        return "GARNI HTTP / WSLink"

    def closePort(self):
        log.info("Stopping %s HTTP server", DRIVER_NAME)
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception as e:
            log.error("Error while stopping HTTP server: %s", e)

    def genLoopPackets(self):
        while True:
            packet = self.packet_queue.get()
            yield packet

    def _make_handler(self):
        driver = self

        class GarniRequestHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == "/status":
                    self._send_json({
                        "status": "ok",
                        "driver": DRIVER_NAME,
                        "version": DRIVER_VERSION,
                        "queue_size": driver.packet_queue.qsize(),
                        "last_packet_ts": driver.last_packet_ts,
                    })
                    return

                if parsed.path != driver.path:
                    self._send_json({"status": "error", "message": "wrong path"}, 404)
                    return

                data = {
                    key: values[0] if isinstance(values, list) and values else values
                    for key, values in parse_qs(parsed.query).items()
                }

                driver.handle_payload(data)
                self._send_json({"status": "ok"})

            def do_POST(self):
                parsed = urlparse(self.path)

                if parsed.path != driver.path:
                    self._send_json({"status": "error", "message": "wrong path"}, 404)
                    return

                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length).decode("utf-8", errors="replace")
                content_type = self.headers.get("Content-Type", "")

                try:
                    if "application/json" in content_type:
                        data = json.loads(raw_body)
                    else:
                        data = {
                            key: values[0] if isinstance(values, list) and values else values
                            for key, values in parse_qs(raw_body).items()
                        }
                except Exception as e:
                    log.error("Could not parse incoming GARNI payload: %s", e)
                    self._send_json({"status": "error", "message": str(e)}, 400)
                    return

                driver.handle_payload(data)
                self._send_json({"status": "ok"})

            def _send_json(self, payload, code=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return GarniRequestHandler

    def handle_payload(self, data):
        obs_ts = parse_observation_time(data)
        now = int(time.time())

        if now - obs_ts > self.stale_timeout:
            log.warning("Ignoring stale GARNI packet. age=%s seconds payload=%s", now - obs_ts, data)
            return

        packet = {
            "dateTime": obs_ts,
            "usUnits": weewx.METRICWX,
        }

        # Indoor values
        add_float(packet, "inTemp", data, ["intem"])
        add_float(packet, "inHumidity", data, ["inhum"])

        # Outdoor channel 1 values
        #
        # Prefer actual temperature if your payload has t1temp.
        # If not, fallback to t1feels/t1heat/t1chill so you still get something.
        add_float(packet, "outTemp", data, ["t1temp", "temp", "outtemp", "t1feels", "t1heat", "t1chill"])
        add_float(packet, "outHumidity", data, ["t1hum", "hum", "outhum"])
        add_float(packet, "dewpoint", data, ["t1dew"])
        add_float(packet, "windchill", data, ["t1chill"])
        add_float(packet, "heatindex", data, ["t1heat"])

        # Pressure
        #
        add_float(packet, "pressure", data, ["abar"])

        # Wind, if present in the GARNI/WSLink payload
        #add_float(packet, "windSpeed", data, ["wind", "wspeed", "wind_speed", "t1wind", "t1windsp"])
        #add_float(packet, "windGust", data, ["gust", "wgust", "wind_gust", "t1gust"])
        #add_float(packet, "windDir", data, ["wdir", "winddir", "wind_dir", "t1wdir"])
        add_float(packet, "windSpeed", data, ["t1ws"])
        add_float(packet, "windGust", data, ["t1wgust"])
        add_float(packet, "windDir", data, ["t1wdir"])

        #UV
        add_float(packet, "radiation", data, ["t1solrad"])
        add_float(packet, "UV", data, ["t1uvi"])

        #Lightning
        packet["lightning_distance"] = get_float(data, ["t5lskm"])
        packet["lightningCount5m"] = get_float(data, ["t5ls5mtc"])
        packet["lightningCount30m"] = get_float(data, ["t5ls30mtc"])
        packet["lightningCount1h"] = get_float(data, ["t5ls1htc"])
        packet["lightningCount1d"] = get_float(data, ["t5ls1dtc"])

        #WGBT
        add_float(packet, "wbgt", data, ["t1wbgt"])

        # Rain
        #
        # WeeWX field "rain" should be the amount since the previous LOOP packet.
        # GARNI t1raindy appears to be daily accumulated rain in mm, so we calculate
        # the delta here.
        rain_day = get_float(data, ["t1raindy", "rainday", "rain_day"])
        if rain_day is not None:
            if self.last_rain_day is None:
                rain_delta = 0.0
            else:
                rain_delta = rain_day - self.last_rain_day

                # Daily counter reset or station reset.
                if rain_delta < 0:
                    rain_delta = 0.0

            self.last_rain_day = rain_day
            packet["rain"] = rain_delta
            packet["dayRain"] = rain_day

        add_float(packet, "rainRate", data, ["t1rainra", "rainrate", "rain_rate"])
        add_float(packet, "hourRain", data, ["t1rainhr", "rainhr", "rain_hour"])
        add_float(packet, "monthRain", data, ["t1rainmth", "rainmth", "rain_month"])
        add_float(packet, "yearRain", data, ["t1rainwy", "rainwy", "rain_year"])

        # Optional diagnostics. These will only be stored if your WeeWX schema has fields for them.
        #add_float(packet, "extraTemp1", data, ["t1feels"])
        #add_float(packet, "extraTemp2", data, ["t1dew"])     

        # Battery/status values
        #
        add_int(packet, "outdoorBatteryOk", data, ["t1bat"])
        add_int(packet, "consoleBatteryOk", data, ["inbat"])
        add_int(packet, "lightningBatteryOk", data, ["t5lsbat"])
        add_int(packet, "outdoorSensorConnected", data, ["t1cn"])
        add_int(packet, "lightningSensorConnected", data, ["t5lscn"])

        self.last_packet_ts = obs_ts

        try:
            self.packet_queue.put_nowait(packet)
            log.info("Queued GARNI packet: %s", packet)
        except queue.Full:
            dropped = self.packet_queue.get_nowait()
            log.warning("Packet queue full. Dropping oldest packet: %s", dropped)
            self.packet_queue.put_nowait(packet)


def parse_observation_time(data):
    """
    Prefer station/WSLink timestamp if available.
    Fallback to receiver time.
    """

    raw = data.get("datetime") or data.get("station_datetime") or data.get("dateTime")

    if raw:
        raw = str(raw).strip()

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
        ):
            try:
                return int(datetime.strptime(raw, fmt).timestamp())
            except Exception:
                pass

        try:
            return int(float(raw))
        except Exception:
            pass

    for key in ("received_ts", "received", "_received_ts"):
        if key in data:
            try:
                return int(float(data[key]))
            except Exception:
                pass

    return int(time.time())


def get_float(data, keys):
    for key in keys:
        if key not in data:
            continue

        value = data.get(key)

        if value in ("", None):
            continue

        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None

    return None


def add_float(packet, weewx_field, data, keys):
    value = get_float(data, keys)
    if value is not None:
        packet[weewx_field] = value

def add_int(packet, weewx_field, data, keys):
    value = get_float(data, keys)
    if value is not None:
        packet[weewx_field] = int(value)
