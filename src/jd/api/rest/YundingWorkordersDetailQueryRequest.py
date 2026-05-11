from jd.api.base import RestApi

class YundingWorkordersDetailQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.querySecurityCenterWorkOrderListVO = None

		def getapiname(self):
			return 'jingdong.yunding.workorders.detail.query'

			
	

class QuerySecurityCenterWorkOrderListVO(object):
		def __init__(self):
			"""
			"""
			self.eventLevel = None
			self.size = None
			self.endDate = None
			self.eventType = None
			self.page = None
			self.startDate = None
			self.status = None





