# (c) 2018-2020 The Tunfish Developers
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from pathlib import Path
from typing import Union

import json5
import uritools


@dataclass
class BusSettings:

    # The URL to the CA for automatically signing a CSR.
    ca_url: uritools.SplitResult = None
    ca_name: str = None

    # The WAMP broker to connect to.
    broker_url: uritools.SplitResult = None

    # Private key and node certificate for encryption and authentication.
    private_key_path: Path = None
    certificate_path: Path = None
    cacert_path: str = None


@dataclass
class WireGuardSettings:
    """
    Settings for WireGuard.

    https://wiki.archlinux.org/index.php/WireGuard#Client_config
    """

    # Where to dial into.
    endpoint: uritools.SplitResult = None

    # Private and public keys.
    private_key: str = None
    public_key: str = None

    # The node IP address.
    address: Union[IPv4Network, IPv6Network] = None

    # Network name.
    # TODO: Where do we use it?
    network_name: str = None


@dataclass
class TunfishClientSettings:

    path: Path = None
    device_id: str = None
    bus: BusSettings = field(default_factory=BusSettings)
    wireguard: WireGuardSettings = field(default_factory=WireGuardSettings)

    def load(self, filename: Path):

        filename = filename.resolve().absolute()
        configfile_name = filename.stem
        configfile_path = filename.parent

        settings = {}
        with open(filename, "r") as f:
            settings = json5.load(f)
            self.path = filename

        version = int(settings.get("version", "1"))

        if version == 1:

            self.device_id = settings.get("device_id")

            bus_settings = settings.get("bus", {})
            if "ca_url" in bus_settings:
                self.bus.ca_url = uritools.urisplit(bus_settings["ca_url"])
            if "ca_name" in bus_settings:
                self.bus.ca_name = bus_settings["ca_name"]
            if "broker" in bus_settings:
                self.bus.broker_url = uritools.urisplit(bus_settings["broker"])
            if "key" in bus_settings:
                self.bus.private_key_path = configfile_path / bus_settings["key"]
            if "cert" in bus_settings:
                self.bus.certificate_path = configfile_path / bus_settings["cert"]
            if "cacert" in bus_settings:
                self.bus.cacert_path = configfile_path / bus_settings["cacert"]

            wireguard_settings = settings.get("wireguard", {})
            if "endpoint" in wireguard_settings:
                self.wireguard.endpoint = uritools.urisplit(
                    "null://" + wireguard_settings["endpoint"]
                )
            if "private_key" in wireguard_settings:
                self.wireguard.private_key = wireguard_settings["private_key"]
            if "public_key" in wireguard_settings:
                self.wireguard.public_key = wireguard_settings["public_key"]
            if "address" in wireguard_settings:
                self.wireguard.address = IPv4Network(wireguard_settings["address"])
            if "network" in wireguard_settings:
                self.wireguard.network_name = wireguard_settings["network"]

        # Fill in the gaps.
        if not self.bus.private_key_path:
            self.bus.private_key_path = configfile_path / f"{configfile_name}-bus.key"
        if not self.bus.certificate_path:
            self.bus.certificate_path = configfile_path / f"{configfile_name}-bus.pem"
        if not self.bus.cacert_path:
            self.bus.cacert_path = configfile_path / f"cacert-bus.pem"
