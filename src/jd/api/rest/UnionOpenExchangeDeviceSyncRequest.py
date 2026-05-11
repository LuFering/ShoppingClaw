from jd.api.base import RestApi

class UnionOpenExchangeDeviceSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.deviceReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.device.sync'

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
			self.eventType = None
			self.deviceId = None
			self.taskId = None
			self.contentId = None
			self.subEventType = None
			self.eventId = None
			self.encryptType = None
			self.campaignId = None
			self.unitId = None
			self.creativeId = None
			self.businessType = None


class DeviceReq(object):
		def __init__(self):
			"""
			"""
			self.deviceInfoList = None
			self.uuid = None





