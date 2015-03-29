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

from azure.servicebus import _service_bus_error_handler
from azure.servicebus.servicebusservice import ServiceBusService, ServiceBusSASAuthentication
from azure.http import HTTPRequest, HTTPError
from azure.http.httpclient import _HTTPClient


class EventHubClient(object):
    '''
    @classmethod
    def write_config(cls, values, path):
    '''

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

    def _apply_config(self, config):
        self._check_config(config)
        for key, value in config.items():
            setattr(self, key, value)

    def __init__(self, config_path = None, config = None):
        assert config_path or config, 'A config is required.'
        
        if config_path:
            config = self.load_config(config_path)

        self._apply_config(config)
        
        self.hostname = socket.gethostname()

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

        return status

    def send_measurement(self, payload, sensor_id):
        return self.send_message(json.dumps(payload), sensor_id)


class Telementry:

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

hubClient = EventHubClient(config_path=config_path)
sensor = Telementry('Device-50')
payload = sensor.measure()
print 'Payload', json.dumps(payload, indent=2)
print 'Response HTTP', hubClient.send_measurement(payload, sensor.device_id)
