from jd.api.base import RestApi

class UnionOpenExchangeDeviceSupplyRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.supplyDeviceReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.device.supply'

		def get_version(self):
			return '1.0'
			
	

class DeviceInfo(object):
		def __init__(self):
			"""
			"""
			self.deviceType = None
			self.orderId = None
			self.requestId = None
			self.eventTime = None
			self.contentId = None
			self.eventType = None
			self.deviceId = None
			self.taskId = None


class SupplyDeviceReq(object):
		def __init__(self):
			"""
			"""
			self.uuid = None
			self.deviceInfoList = None





