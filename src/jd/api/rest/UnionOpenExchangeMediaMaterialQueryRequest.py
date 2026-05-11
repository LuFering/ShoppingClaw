from jd.api.base import RestApi

class UnionOpenExchangeMediaMaterialQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.AuthMaterialQueryReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.material.query'

		def get_version(self):
			return '1.0'
			
	

class AuthMaterialQueryReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.startTime = None
			self.endTime = None





