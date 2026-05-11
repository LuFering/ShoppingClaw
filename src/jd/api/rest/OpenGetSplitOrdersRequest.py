from jd.api.base import RestApi

class OpenGetSplitOrdersRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.beginTime = None
			self.endTime = None
			self.orderState = None

		def getapiname(self):
			return 'jingdong.open.getSplitOrders'

			





