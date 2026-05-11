from jd.api.base import RestApi

class UnionOpenCpActivityInfoQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityInfoQueryReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.info.query'

		def get_version(self):
			return '1.0'
			
	

class CpActivityInfoQueryReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None





