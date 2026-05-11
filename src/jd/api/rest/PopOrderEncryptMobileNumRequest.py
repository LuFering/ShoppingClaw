from jd.api.base import RestApi

class PopOrderEncryptMobileNumRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.mobile = None

		def getapiname(self):
			return 'jingdong.pop.order.encryptMobileNum'

			





