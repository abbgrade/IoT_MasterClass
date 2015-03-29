#!/user/bin/python

'''
    based on http://blog.kloud.com.au/2014/10/11/the-internet-of-things-with-arduino-azure-event-hubs-and-the-azure-python-sdk/
'''

import sys
import os
import azure
import socket
import json
import random
import logging

logging.basicConfig(level='DEBUG')

from azure.servicebus import _service_bus_error_handler
from azure.servicebus.servicebusservice import ServiceBusService, ServiceBusSASAuthentication
from azure.http import HTTPRequest, HTTPError
from azure.http.httpclient import _HTTPClient


class EventHubClient(object):
    
    _config_keys = ['service_bus_namespace', 'event_hub_name', 'policy_name', 'policy_key']

    @classmethod
    def _check_config(cls, config):
        for key in cls._config_keys:
            assert key in config.keys(), 'The key %s is an expected element of the configuration %s' % (key, config)

        for key in config.keys():
            assert key in cls._config_keys, 'The key %s is an unexpected element of the configuration %s' % (key, config)

    @classmethod
    def save_config(cls, path, force = True, **config):
        cls._check_config(config)

        if not os.path.exists(path) or force:
            with open(path, 'wb') as file_handle:
                json.dump(config, file_handle, indent = 2)

    @classmethod
    def load_config(cls, path):
        with open(path, 'rb') as file_handle:
            return json.load(file_handle)

    @property
    def config(self):
        config = {}

        for key in self._config_keys:
            config[key] = getattr(self, key)

        return config
    
    @config.setter
    def config(self, config):
        self._check_config(config)

        for key, value in config.items():
            setattr(self, key, value)

    def __init__(self, config_path = None, config = None, max_error_count = 0):
        assert config_path or config, 'A config is required.'
        
        if config_path:
            config = self.load_config(config_path)

        self.config = config
        self.hostname = socket.gethostname()
        self.error_count = 0
        self.max_error_count = max_error_count

    def send_message(self, body, partition):
        httpclient = _HTTPClient(service_instance=self)

        # build request
        request = HTTPRequest()
        request.method = 'POST'
        request.host = '%s.servicebus.windows.net' % self.service_bus_namespace
        request.protocol_override = 'https'
        request.path = '/%s/publishers/%s/messages?api-version=2014-05' % (self.event_hub_name, partition)
        request.body = body
        request.headers.append(('Content-Type', 'application/atom+xml;type=entry;charset=utf-8'))

        logging.debug('%s "%s" to %s://%s%s', request.method, body, request.protocol_override, request.host, request.path)
    
        # authenticate request
        authentication = ServiceBusSASAuthentication(self.policy_name, self.policy_key)
        authentication.sign_request(request, httpclient)

        # verify request
        request.headers.append(('Content-Length', str(len(request.body))))

        # send request
        status = 0

        try:
            resp = httpclient.perform_request(request)
            status = resp.status

        except HTTPError as ex:
            status = ex.status
            self.error_count += 1
            if self.error_count > self.max_error_count:
                raise

        return status

    def send_measurement(self, payload, sensor_id):
        return self.send_message(json.dumps(payload), sensor_id)


class Telemetry:

    def __init__(self, device_id):
        self.device_id = device_id

    def measure(self):
        return {
            'DeviceId': self.device_id,
            'Temperature': 27.5,
            'Humidity': 68.3,
            'Pollution': random.random() * 100
        }


config_path = 'event_hub_config.json'
EventHubClient.save_config(config_path,
                           force = False, 
                           service_bus_namespace = 'myservicebusnamespace', 
                           event_hub_name = 'myhub', 
                           policy_name = 'SendPolicy', 
                           policy_key = 'erENqf/5wdWCNEbCA9NsDIRqd5MRKdkii07+wezl/NU=')

hub_client = EventHubClient(config_path=config_path)
print 'EventHub', json.dumps(hub_client.config, indent = 2)

# now the fancy stuff begins

import threading
import time

sensor_count = 10
measurement_interval = 10
measurement_iterations = 10

class Device(Telemetry, threading.Thread):

    def __init__(self, device_id, hub_client, interval, iterations):
        Telemetry.__init__(self, device_id)
        threading.Thread.__init__(self)

        self.hub_client = hub_client
        self.interval = interval
        self.iterations = iterations

    def run(self):
        for iteration in xrange(self.iterations):
            payload = self.measure()
            response = self.hub_client.send_measurement(payload, self.device_id)
            time.sleep(self.interval)


devices = [Device(device_id, hub_client, measurement_interval, measurement_iterations) for device_id in ['Device-%d' % index for index in range(1, 1 + sensor_count,)]]
random.shuffle(devices)

for device in devices:
    device.start()
    time.sleep(1) # for a little asyncronity

for thread in devices:
    thread.join()