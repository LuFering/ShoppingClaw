from jd.api.base import RestApi

class UnionOpenOrderBonusQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.orderReq = None

		def getapiname(self):
			return 'jd.union.open.order.bonus.query'

		def get_version(self):
			return '1.0'
			
	

class OrderReq(object):
		def __init__(self):
			"""
			"""
			self.optType = None
			self.startTime = None
			self.endTime = None
			self.pageNo = None
			self.pageSize = None
			self.sortValue = None
			self.activityId = None





