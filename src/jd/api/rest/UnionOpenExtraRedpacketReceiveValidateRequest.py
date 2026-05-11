from jd.api.base import RestApi

class UnionOpenExtraRedpacketReceiveValidateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.req = None

		def getapiname(self):
			return 'jd.union.open.extra.redpacket.receive.validate'

		def get_version(self):
			return '1.0'
			
	

class Req(object):
		def __init__(self):
			"""
			"""
			self.userId = None
			self.userIdType = None
			self.actId = None





