from jd.api.base import RestApi

class TradeDqgPlanListQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.planParam = None

		def getapiname(self):
			return 'jingdong.trade.dqg.plan.list.query'

			
	

class PlanParam(object):
		def __init__(self):
			"""
			"""
			self.startRow = None
			self.planStartTime = None
			self.payMode = None
			self.pageSize = None
			self.planEndTime = None
			self.skuId = None
			self.planNumber = None





