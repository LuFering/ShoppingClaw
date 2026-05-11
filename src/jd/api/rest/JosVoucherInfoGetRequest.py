from jd.api.base import RestApi

class JosVoucherInfoGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.access_token = None
			self.customer_user_id = None

		def getapiname(self):
			return 'jingdong.jos.voucher.info.get'

			





