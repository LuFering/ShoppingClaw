from jd.api.base import RestApi

class KplOpenPolcenterUnsubscribemobileRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.request = None

		def getapiname(self):
			return 'jd.kpl.open.polcenter.unsubscribemobile'

		def get_version(self):
			return '1.0'
			
	

class Request(object):
		def __init__(self):
			"""
			"""
			self.mobile = None
			self.factoryId = None
			self.androidId = None
			self.imei = None
			self.wifiMac = None
			self.clientIp = None
			self.bussName = None
			self.orderNum = None





