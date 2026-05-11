from jd.api.base import RestApi

class BizAreaGetJDAddressFromAddressRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.address = None

		def getapiname(self):
			return 'jingdong.biz.area.getJDAddressFromAddress'

			





