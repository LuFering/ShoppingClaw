from jd.api.base import RestApi

class UnionOpenCpActivityQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityListQueryReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.query'

		def get_version(self):
			return '1.0'
			
	

class CpActivityListQueryReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None
			self.pageIndex = None
			self.activityStatus = None
			self.pageSize = None
			self.title = None





