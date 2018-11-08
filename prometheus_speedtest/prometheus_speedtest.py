#!/usr/bin/python3
"""Instrument speedtest.net speedtests from Prometheus."""

import argparse
import http
import os
import socketserver
import urllib

import glog as logging
import speedtest

import prometheus_client

PARSER = argparse.ArgumentParser(
    description='Instrument speedtest.net speedtests from Prometheus.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
PARSER.add_argument(
    '-p',
    '--port',
    metavar='port',
    default=8080,
    type=int,
    help='port to listen on')

FLAGS = PARSER.parse_args()


class PrometheusSpeedtest:
    """Enapsulates behavior performing and reporting results of speedtests."""

    def __init__(self, source_address=None, timeout=10):
        """Instantiates a PrometheusSpeedtest object.

        Args:
            source_address: str - optional network address to bind to.
                e.g. 192.168.1.1.
            timeout: int - optional timeout for speedtest in seconds.
        """
        self._source_address = source_address
        self._timeout = timeout

    def test(self):
        """Performs speedtest, returns results.

        Returns:
            speedtest.SpeedtestResults object.
        """
        logging.info('Performing Speedtest')
        client = speedtest.Speedtest(
            source_address=self._source_address, timeout=self._timeout)
        client.get_best_server()
        client.download()
        client.upload()
        logging.info(client.results)
        return client.results


class SpeedtestCollector:
    """Performs Speedtests when requested from Prometheus."""

    def __init__(self, tester=None):
        """Instantiates a SpeedtestCollector object.

        Args:
            tester: An instantiated PrometheusSpeedtest object for testing.
        """
        self._tester = tester if tester else PrometheusSpeedtest()

    def collect(self):
        """Performs a Speedtests and yields metrics.

        Yields:
            core.Metric objects.
        """
        results = self._tester.test()

        download_speed = prometheus_client.core.GaugeMetricFamily(
            'download_speed_bps', 'Download speed (bit/s)')
        download_speed.add_metric(labels=[], value=results.download)
        yield download_speed

        upload_speed = prometheus_client.core.GaugeMetricFamily(
            'upload_speed_bps', 'Upload speed (bit/s)')
        upload_speed.add_metric(labels=[], value=results.upload)
        yield upload_speed

        ping = prometheus_client.core.GaugeMetricFamily('ping_ms',
                                                        'Latency (ms)')
        ping.add_metric(labels=[], value=results.ping)
        yield ping

        bytes_received = prometheus_client.core.GaugeMetricFamily(
            'bytes_received', 'Bytes received during test')
        bytes_received.add_metric(labels=[], value=results.bytes_received)
        yield bytes_received

        bytes_sent = prometheus_client.core.GaugeMetricFamily(
            'bytes_sent', 'Bytes sent during test')
        bytes_sent.add_metric(labels=[], value=results.bytes_sent)
        yield bytes_sent


class SpeedtestMetricsHandler(http.server.SimpleHTTPRequestHandler,
                              prometheus_client.MetricsHandler):
    """HTTP handler extending MetricsHandler and adding status page support."""

    def do_GET(self):
        """Handles HTTP GET requests.

        Requests to '/probe' are handled by prometheus_client.MetricsHandler,
        other requests serve static HTML.
        """
        path = urllib.parse.urlparse(self.path).path
        if path == '/probe':
            prometheus_client.MetricsHandler.do_GET(self)
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)


def main():
    """Entry point for prometheus_speedtest.py."""
    registry = prometheus_client.core.CollectorRegistry(auto_describe=False)
    registry.register(SpeedtestCollector())
    metrics_handler = SpeedtestMetricsHandler.factory(registry)

    # http.server.ThreadingHTTPServer is new to Python 3.7, create our own for
    # backwards-compatibility.
    threading_http_server = type(
        'ThreadingHTTPServer',
        (socketserver.ThreadingMixIn, http.server.HTTPServer), {})
    server = threading_http_server(('', FLAGS.port), metrics_handler)

    # http.server.SimpleHTTPRequestHandler added support for a directory
    # argument in Python 3.7. Change directory here for backwards
    # compatibility with older versions of Python 3.
    os.chdir(os.path.join(os.path.dirname(__file__), 'static'))

    logging.info('Starting HTTP server on port %s', FLAGS.port)
    server.serve_forever()


if __name__ == '__main__':
    main()
