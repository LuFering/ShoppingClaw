from jd.api.base import RestApi

class UnionOpenExchangeDeviceFileQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.deviceFileQueryReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.device.file.query'

		def get_version(self):
			return '1.0'
			
	

class DeviceFileQueryReq(object):
		def __init__(self):
			"""
			"""
			self.activeDate = None
			self.uuid = None





