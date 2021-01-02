# (c) 2018-2020 The Tunfish Developers
import asyncio
import logging
import os
import ssl
import time
from functools import partial
from pathlib import Path

import appdirs
import click
import json5
import six
from autobahn.asyncio.wamp import ApplicationRunner, ApplicationSession
from pyroute2 import IPRoute

from tunfish.client.crypto import AsymmetricKey
from tunfish.client.model import WireGuardInterface
from tunfish.client.util import setup_logging

logger = logging.getLogger(__name__)


class TunfishClientSession(ApplicationSession):

    def __init__(self, *args, **kwargs):
        super(TunfishClientSession, self).__init__(*args, **kwargs)
        self.tfcfg = self.config.extra["tunfish_settings"]

    async def onJoin(self, details):

        def got(started, msg, ff):
            logger.info(f"result received")
            res = ff.result()
            duration = 1000. * (time.process_time() - started)
            logger.info("{}: {} in {}".format(msg, res, duration))
            if msg == "REQUEST GATEWAY":
                # TODO: open interface

                interface = WireGuardInterface()

                ip_and_mask = f"{self.tfcfg['ip']}/{self.tfcfg['mask']}"

                # new interface/wg control
                logger.info(f"new control")
                interface.create(ifname=self.tfcfg['device_id'], ip=ip_and_mask, privatekey=self.tfcfg['wgprvkey'], listenport=42001)
                interface.addpeer(ifname=self.tfcfg['device_id'], publickey=res['wgpubkey'], endpointaddr=res['endpoint'], endpointport=res['listen_port'], keepalive=10, allowedips={'0.0.0.0/0'})

                # TODO: Maybe refactor all of this into "WireGuardInterface"...
                device = IPRoute()

                # set rule
                # router.dev.rule('del', table=10, src='192.168.100.10/24')
                # router.dev.rule('add', table=10, src='172.16.100.15/16')
                # router.dev.rule('add', table=10, src='10.0.23.15/16')
                device.rule('add', table=10, src=ip_and_mask)
                # set route
                # router.dev.route('del', table=10, src='192.168.100.10/24', oif=idx)
                idx = device.link_lookup(ifname=self.tfcfg['device_id'])[0]
                device.route('add', table=10, src='10.0.42.15/16', gateway='10.0.23.15', oif=idx)

                # iptables
                import iptc
                chain = iptc.Chain(iptc.Table(iptc.Table.NAT), "POSTROUTING")
                rule = iptc.Rule()
                rule.out_interface = "tf-0815"
                target = iptc.Target(rule, "MASQUERADE")
                rule.target = target
                chain.insert_rule(rule)

        t1 = time.process_time()

        # task = self.call(u'com.portier.requestgateway', self.tfcfg, options=CallOptions(timeout=0))
        task = self.call(u'com.portier.request_gateway', self.tfcfg)
        task.add_done_callback(partial(got, t1, "REQUEST GATEWAY"))
        await asyncio.gather(task)

        t1 = time.process_time()
        task = self.call(u'com.portier.request_status')
        task.add_done_callback(partial(got, t1, "REQUEST STATUS"))
        await asyncio.gather(task)

        self.leave()

    def onDisconnect(self):
        # delete interface
        # reconnect
        asyncio.get_event_loop().stop()


class TunfishClient:

    appname = "tunfish-client"

    # TODO: Make autosign URL configurable.
    autosign_url = "http://localhost:8000/pki/autosign"

    def __init__(self, config_file: Path):

        self.config_path: Path = Path(appdirs.user_config_dir(self.appname))
        self.config_path.mkdir(parents=True, exist_ok=True)

        self.private_key_path: Path = self.config_path / "bus.key"
        self.certificate_path: Path = self.config_path / "bus.pem"

        self.settings: dict = None
        with open(config_file, 'r') as f:
            self.settings = json5.load(f)

        self.autocrypt()

    def autocrypt(self):
        """
        Generate X.509 material and autosign it at CA.
        """

        # TODO: Check if certificate is about to expire.

        if not (self.private_key_path.exists() and self.certificate_path.exists()):
            logger.info(f"Generating X.509 material to {self.config_path}")

            try:
                akey = AsymmetricKey()
                akey.make_rsa_key()
                akey.make_csr()

                akey.submit_csr(self.autosign_url)

                akey.save_key(self.private_key_path)
                akey.save_cert(self.certificate_path)
            except Exception as ex:
                logger.error(f"Generating X.509 material failed: {ex}")

    def start(self):

        # url = os.environ.get("AUTOBAHN_DEMO_ROUTER", u"wss://127.0.0.1:8080/ws")
        url = os.environ.get("AUTOBAHN_DEMO_ROUTER", u"wss://172.16.42.2:8080/ws")
        logger.info(f"Connecting to broker address {url}")
        if six.PY2 and type(url) == six.binary_type:
            url = url.decode('utf8')
        realm = u"tf_cb_router"
        runner = ApplicationRunner(url, realm, ssl=self.make_ssl_context(), extra={'tunfish_settings': self.settings})
        runner.run(TunfishClientSession)

    def make_ssl_context(self):

        logger.info(f"Loading X.509 material from {self.config_path}")

        if not self.certificate_path.exists():
            logger.error(f"File not found: {self.certificate_path}")

        if not self.private_key_path.exists():
            logger.error(f"File not found: {self.private_key_path}")

        client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        client_ctx.verify_mode = ssl.CERT_REQUIRED
        client_ctx.options |= ssl.OP_SINGLE_ECDH_USE
        client_ctx.options |= ssl.OP_NO_COMPRESSION
        client_ctx.load_cert_chain(certfile=self.certificate_path, keyfile=self.private_key_path)
        #client_ctx.load_verify_locations(cafile=caf)
        client_ctx.set_ciphers('ECDH+AESGCM')

        return client_ctx


@click.command(help="""Bootstrap and maintain connection to Tunfish network.""")
@click.option("--config",
              type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help="The configuration file",
              required=True)
def start(config: Path):
    setup_logging(logging.DEBUG)
    client = TunfishClient(config_file=config)
    client.start()
