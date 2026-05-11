from jd.api.base import RestApi

class UnionOpenActivityBonusQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.req = None

		def getapiname(self):
			return 'jd.union.open.activity.bonus.query'

		def get_version(self):
			return '1.0'
			
	

class Req(object):
		def __init__(self):
			"""
			"""
			self.activityId = None
			self.beginTime = None
			self.endTime = None
			self.pageIndex = None
			self.pageSize = None





