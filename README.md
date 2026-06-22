This repo provides a stable, but experimental driver for several Garni stations.
It utilizes the "custom server" option that the consoles and the gateway provide.

The custom weather server mode sends data in TLS to the IP you specify to a webserver of your choice (nginx, apache, caddy) with a (self-signed) certificate
this in turn send the data into the weewx driver listening on a TCP port.

This way you can easily read all data that is provided by Garni directly into Weewx.

Elements required:

* Linux machine running weewx
* Webserver with a (self-signed) certificate
* Configuration on your Garni station
* The custom weewx Garni driver
* Some weewx tweaks


