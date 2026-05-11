from jd.api.base import RestApi

class UnionOpenActivityQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.activityReq = None

		def getapiname(self):
			return 'jd.union.open.activity.query'

		def get_version(self):
			return '1.0'
			
	

class ActivityReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.poolId = None
			self.activeDate = None





