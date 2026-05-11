from jd.api.base import RestApi

class UnionOpenCpPersonalInfoQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpPersonalInfoQueryReq = None

		def getapiname(self):
			return 'jd.union.open.cp.personal.info.query'

		def get_version(self):
			return '1.0'
			
	

class CpPersonalInfoQueryReq(object):
		def __init__(self):
			"""
			"""
			self.fields = None





