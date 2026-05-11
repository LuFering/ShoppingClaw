from jd.api.base import RestApi

class KplOpenNosecretpaySavetokenRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.req = None
			self.ptKey = None

		def getapiname(self):
			return 'jd.kpl.open.nosecretpay.savetoken'

		def get_version(self):
			return '1.0'
			
	

class Req(object):
		def __init__(self):
			"""
			"""
			self.id = None
			self.deviceId = None
			self.token = None
			self.remarks = None
			self.clientIp = None





