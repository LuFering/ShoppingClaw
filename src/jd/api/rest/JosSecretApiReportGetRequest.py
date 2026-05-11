from jd.api.base import RestApi

class JosSecretApiReportGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.access_token = None
			self.businessId = None
			self.text = None
			self.attribute = None
			self.customer_user_id = None
			self.server_url = None

		def getapiname(self):
			return 'jingdong.jos.secret.api.report.get'

			





