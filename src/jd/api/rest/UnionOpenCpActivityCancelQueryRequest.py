from jd.api.base import RestApi

class UnionOpenCpActivityCancelQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpCancelActivityQueryReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.cancel.query'

		def get_version(self):
			return '1.0'
			
	

class CpCancelActivityQueryReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None
			self.pageIndex = None
			self.pageSize = None
			self.shopName = None
			self.examineStatus = None
			self.skuId = None





