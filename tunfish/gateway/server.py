import iptc
import pysodium
from tunfish.portier.model import Router

from tunfish.node.model import WireGuardInterface, WireGuardPeer


class GatewayRPC:
    def __init__(self, fabric):
        self.fabric = fabric

    def open_interface(self, data):
        print(f"data: {data}")

        # create keypair
        from base64 import b64encode

        keys = pysodium.crypto_box_keypair()

        # TODO: open interface
        router = Router()

        # self.gateway.router.interface.create(ifname=data['device_id'], ip='10.0.42.15/16', privatekey=b64encode(keys[1]),
        #                        listenport=42001)

        # new interface/wg control
        wi = WireGuardInterface(ifname=data["device_id"], ip="10.0.42.15/16")
        wi.create(privatekey=b64encode(keys[1], listenport=42001))

        # router.interface.addpeer(ifname=data['device_id'], publickey=data['wgpubkey'], endpointaddr=data['ip'], endpointport=42001, keepalive=10)

        peer = WireGuardPeer(
            public_key=data["wgpubkey"],
            allowed_ips={"0.0.0.0/0"},
            persistent_keepalive=10,
        )
        wi.add_peer(peer)

        # iptables for wg-interface
        chain = iptc.Chain(iptc.Table(iptc.Table.FILTER), "FORWARD")
        rule = iptc.Rule()
        rule.out_interface = "tf-0815"
        target = iptc.Target(rule, "ACCEPT")
        rule.target = target
        chain.insert_rule(rule)

        chain = iptc.Chain(iptc.Table(iptc.Table.NAT), "POSTROUTING")
        rule = iptc.Rule()
        rule.out_interface = "eth0"
        target = iptc.Target(rule, "MASQUERADE")
        rule.target = target
        chain.insert_rule(rule)

        return b64encode(keys[0])

        # com.gw.close_interface

    def close_interface(self, data):
        router = Router()
        router.interface.delete(ifname=data["device_id"])
