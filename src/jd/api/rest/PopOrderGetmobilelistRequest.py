from jd.api.base import RestApi

class PopOrderGetmobilelistRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.appName = None
			self.region = None
			self.orderId = None
			self.expiration = None
			self.orderType = None

		def getapiname(self):
			return 'jingdong.pop.order.getmobilelist'

			





