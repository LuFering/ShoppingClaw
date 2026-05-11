from jd.api.base import RestApi

class MfaInnerSendCodeToMobileRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.rKey = None
			self.validateType = None

		def getapiname(self):
			return 'jingdong.mfa.inner.sendCodeToMobile'

			





