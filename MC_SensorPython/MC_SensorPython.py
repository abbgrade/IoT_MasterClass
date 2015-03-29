#!/user/bin/python

'''
	based on http://blog.kloud.com.au/2014/10/11/the-internet-of-things-with-arduino-azure-event-hubs-and-the-azure-python-sdk/
'''

import sys
import azure
import socket
import json
import random

from azure.servicebus import _service_bus_error_handler
from azure.servicebus.servicebusservice import ServiceBusService, ServiceBusSASAuthentication
from azure.http import HTTPRequest, HTTPError
from azure.http.httpclient import _HTTPClient


class EventHubClient(object):

	def __init__(self, service_bus_namespace, event_hub_name, policy_name, policy_key):
		self.hostname = socket.gethostname()
		self.service_bus_namespace, self.event_hub_name = service_bus_namespace, event_hub_name
		self.policy_name, self.policy_key = policy_name, policy_key

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


hubClient = EventHubClient('myservicebusnamespace', 'myhub', 'SendPolicy', 'erENqf/5wdWCNEbCA9NsDIRqd5MRKdkii07+wezl/NU=')
sensor = Telementry('Device-50')
payload = sensor.measure()
print 'Payload', json.dumps(payload, indent=2)
print 'Response HTTP', hubClient.send_measurement(payload, sensor.device_id)
