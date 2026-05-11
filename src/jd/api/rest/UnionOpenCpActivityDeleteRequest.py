from jd.api.base import RestApi

class UnionOpenCpActivityDeleteRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityDeleteReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.delete'

		def get_version(self):
			return '1.0'
			
	

class CpActivityDeleteReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None





