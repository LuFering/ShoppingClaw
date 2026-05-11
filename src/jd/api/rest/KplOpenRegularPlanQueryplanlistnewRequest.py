from jd.api.base import RestApi

class KplOpenRegularPlanQueryplanlistnewRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.planParam = None

		def getapiname(self):
			return 'jd.kpl.open.regular.plan.queryplanlistnew'

		def get_version(self):
			return '1.0'
			
	

class PlanParam(object):
		def __init__(self):
			"""
			"""
			self.startRow = None
			self.pageSize = None
			self.planNumber = None
			self.payMode = None
			self.skuId = None
			self.planStartTime = None
			self.planEndTime = None





