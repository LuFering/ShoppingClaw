from jd.api.base import RestApi

class KplOpenYaoOrdersyncGetorderlistRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.orderId = None

		def getapiname(self):
			return 'jingdong.kpl.open.yao.ordersync.getorderlist'

			





