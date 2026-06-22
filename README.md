# Garni HTTP Driver for WeeWX

This repository provides a stable, but still experimental, driver for several Garni weather stations and gateways.

The driver utilizes the **Custom Weather Server** feature available on supported Garni consoles and gateways.

When configured, the station sends weather data via HTTPS/TLS to a web server of your choice (Nginx, Apache, Caddy, etc.) using a valid or self-signed certificate. The web server forwards the incoming requests to the Garni HTTP driver, which listens locally on a TCP port and injects the observations directly into WeeWX.

This approach allows all available Garni measurements to be archived and processed by WeeWX without relying on third-party cloud services.

## Architecture

```text
Garni Station
      │ HTTPS
      ▼
Nginx / Caddy / Apache
      │ HTTP
      ▼
Garni HTTP Driver (Port 8080)
      │
      ▼
    WeeWX
      │
      ▼
Database / Reports / Skins
```

## Requirements

* Linux system running WeeWX 5.x
* A web server (Nginx, Apache, Caddy, etc.)
* TLS certificate (public CA or self-signed)
* Supported Garni weather station or gateway
* This Garni HTTP driver

## Installation

### 1. Stop WeeWX

```bash
sudo systemctl stop weewx
```

### 2. Add custom database columns

The driver provides several observations that are not part of the standard WeeWX schema.

```bash
sudo weectl database add-column wbgt REAL

sudo weectl database add-column lightning_distance REAL
sudo weectl database add-column lightningCount5m REAL
sudo weectl database add-column lightningCount30m REAL
sudo weectl database add-column lightningCount1h REAL
sudo weectl database add-column lightningCount1d REAL

sudo weectl database add-column outdoorBatteryOk INTEGER
sudo weectl database add-column consoleBatteryOk INTEGER
sudo weectl database add-column lightningBatteryOk INTEGER

sudo weectl database add-column outdoorSensorConnected INTEGER
sudo weectl database add-column lightningSensorConnected INTEGER
```

### 3. Install the driver

```bash
sudo cp garni_http.py /etc/weewx/bin/user/
sudo cp extensions.py /etc/weewx/bin/user/
```

### 4. Configure WeeWX

Add the following sections to `weewx.conf`:

```ini
[Station]
    station_type = GarniHTTP

[GarniHTTP]
    driver = user.garni_http
    host = 127.0.0.1
    port = 8080
    path = /
    stale_timeout = 900
    queue_size = 300
```

### 5. Configure your reverse proxy

Example Nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name weather.example.com;

    ssl_certificate     /etc/ssl/certs/weather.crt;
    ssl_certificate_key /etc/ssl/private/weather.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

### 6. Configure your Garni station

Configure the **Custom Weather Server** settings:

| Setting         | Value                |
| --------------- | -------------------- |
| Protocol        | HTTPS                |
| Host            | Your server hostname |
| Port            | 443                  |
| Path            | /                    |
| Upload Interval | 60 seconds           |

The exact menu names may vary between Garni models.

### 7. Start WeeWX

```bash
sudo systemctl start weewx
```

### 8. Verify operation

Monitor the WeeWX log:

```bash
sudo journalctl -u weewx -f
```

You should see messages similar to:

```text
Queued GARNI packet: {...}
```

The driver also exposes a local status endpoint:

```bash
curl http://127.0.0.1:8080/status
```

Expected response:

```json
{
  "status": "ok",
  "driver": "GarniHTTP",
  "version": "0.2"
}
```

## Supported Observations

* Indoor temperature
* Indoor humidity
* Outdoor temperature
* Outdoor humidity
* Dew point
* Wind chill
* Heat index
* Pressure
* Wind speed
* Wind gust
* Wind direction
* Solar radiation
* UV index
* Rainfall
* WBGT
* Lightning distance
* Lightning strike counters (5m, 30m, 1h, 1d)
* Sensor connection status
* Sensor battery status

## Tested Hardware

The driver has been tested with:

* Garni 3075 Arcus 2NG outdoor Sensors
* Garni Lightning Sensor 072L
* Garni Temperature Sensors 056H
* Garni GTway Plus

Other WSLink-compatible Garni stations may work as well.

## Disclaimer

This driver is not affiliated with Garni.

Use at your own risk. The project is currently considered experimental, although it has been running reliably in production environments.
