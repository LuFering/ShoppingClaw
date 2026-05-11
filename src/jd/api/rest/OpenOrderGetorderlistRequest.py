from jd.api.base import RestApi

class OpenOrderGetorderlistRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.orderId = None

		def getapiname(self):
			return 'jingdong.open.order.getorderlist'

			





