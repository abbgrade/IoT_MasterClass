#!/user/bin/python
# This code is documented with [Pycco](https://github.com/fitzgen/pycco)
# To build the docs run:
# 
#     pycco.exe -p .\MC_SensorPython.py -d doc 

import sys
import os
import azure
import socket
import json
import random
import threading
import time
import logging
logging.basicConfig(level='DEBUG')

from azure.servicebus import _service_bus_error_handler
from azure.servicebus.servicebusservice import ServiceBusService, ServiceBusSASAuthentication
from azure.http import HTTPRequest, HTTPError
from azure.http.httpclient import _HTTPClient

## EventHub Client
    # The EventHubClient manages the transmission of payload to the Azure EventHub.
    # It is based on [a blog post from Olaf Loogman](http://blog.kloud.com.au/2014/10/11/the-internet-of-things-with-arduino-azure-event-hubs-and-the-azure-python-sdk/)

class EventHubClient(object):
    
    ### EventHub Config
    # The configuration consists of four strings: the service bus namespace, the event hub name, the policy name and the policy key.
    # It has the form of a dict and can be loaded from and persisted to a JSON file with the classmethods load_config and save_config.
    # It can be applied to the instance by setting a dict to self.config an can be exported by reading self.config .
    
    _config_keys = ['service_bus_namespace', 'event_hub_name', 'policy_name', 'policy_key']

    @classmethod
    def _check_config(cls, config):
        for key in cls._config_keys:
            assert key in config.keys(), 'The key %s is an expected element of the configuration %s' % (key, config)

        for key in config.keys():
            assert key in cls._config_keys, 'The key %s is an unexpected element of the configuration %s' % (key, config)

    @classmethod
    def load_config(cls, path):
        with open(path, 'rb') as file_handle:
            return json.load(file_handle)

    @classmethod
    def save_config(cls, path, force = True, **config):
        cls._check_config(config)

        if not os.path.exists(path) or force:
            with open(path, 'wb') as file_handle:
                json.dump(config, file_handle, indent = 2)

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

    ### Constructor
    # A valid configuration is required. It can be passed by a dict at the config parameter or as a path to a JSON file at the config_path parameter.
    # The max error count parameter is optional. It sets the number of non succesful requests to bring the client to an exception.

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

        # The HTTPS POST request has to be set up with host, path and body, authenticated with SAS.

        request = HTTPRequest()
        request.method = 'POST'
        request.host = '%s.servicebus.windows.net' % self.service_bus_namespace
        request.protocol_override = 'https'
        request.path = '/%s/publishers/%s/messages?api-version=2014-05' % (self.event_hub_name, partition)
        request.body = body
        request.headers.append(('Content-Type', 'application/atom+xml;type=entry;charset=utf-8'))

        authentication = ServiceBusSASAuthentication(self.policy_name, self.policy_key)
        authentication.sign_request(request, httpclient)

        request.headers.append(('Content-Length', str(len(request.body))))

        # After the execution, the response status has to be processed and if the max error limit is reached, the exception has to be escalated.

        status = 0
        try:
            resp = httpclient.perform_request(request)
            status = resp.status
        
        except HTTPError as ex:
            status = ex.status
            self.error_count += 1
            if self.error_count > self.max_error_count:
                raise

        finally:
            logging.debug('%s "%s" to %s://%s%s -> %d', request.method, body, request.protocol_override, request.host, request.path, status)
        
        return status


## Example
# The test case is that a few individual sensors produce temperature, humindity and pollution values, that have to be send to the EventHub.

### The Telemetry Class
# The telemetry class just generates the values and returns them on demand.

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


### The TelemetryHubClient Class
# The TelemetryHubClient extends the EventHubClient with an method to send measurements.

class TelemetryHubClient(EventHubClient):

    def send_measurement(self, measurement, sensor_id):
        return self.send_message(json.dumps(measurement), sensor_id)

    
### The Device Class
# The Device mimics the operating system of a data generating device.
# It runs in a thread and measures in a given interval for given number of iterations.

class Device(Telemetry, threading.Thread):

    def __init__(self, device_id, hub_client, interval, iterations):
        Telemetry.__init__(self, device_id)
        threading.Thread.__init__(self)

        self.hub_client = hub_client
        self.interval = interval
        self.iterations = iterations

    def run(self):
        for iteration in xrange(self.iterations):
            try:
                payload = self.measure()
                response = self.hub_client.send_measurement(payload, self.device_id)
        
            except:
                logging.debug('%s stopped working.', self.device_id)
                return

            time.sleep(self.interval)

        logging.debug('%s finished measurment sequence.', self.device_id)


## Script

if __name__ == "__main__":
    
    # If no configuration exists create one in the local directory.

    config_path = 'event_hub_config.json'
    
    TelemetryHubClient.save_config(
        config_path,
        force = False, 
        service_bus_namespace = 'myservicebusnamespace', 
        event_hub_name = 'myhub', 
        policy_name = 'SendPolicy', 
        policy_key = 'erENqf/5wdWCNEbCA9NsDIRqd5MRKdkii07+wezl/NU=')

    # Instantiate a client and the active config to debug purposes

    hub_client = TelemetryHubClient(config_path=config_path)
    print 'EventHub', json.dumps(hub_client.config, indent = 2)

    # Configure the number and properties of the devices and instantiate them.

    sensor_count = 10
    measurement_interval = 10
    measurement_iterations = 100

    devices = [
        Device(device_id, hub_client, measurement_interval, measurement_iterations) 
        for device_id 
        in [
            'Device-%d' % index 
            for index 
            in range(1, 1 + sensor_count)
            ]
        ]
    random.shuffle(devices) # for a little nondeterminism

    for device in devices:
        device.start()
        time.sleep(1) # for a little asyncronity

    # Wait until the last device stops.

    for thread in devices:
        thread.join()