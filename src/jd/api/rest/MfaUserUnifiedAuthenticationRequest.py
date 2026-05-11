from jd.api.base import RestApi

class MfaUserUnifiedAuthenticationRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.returnUrl = None
			self.deviceOSType = None
			self.appId = None
			self.businessType = None
			self.eid = None
			self.openUDID = None
			self.source = None
			self.deviceName = None
			self.email = None
			self.deviceOSVersion = None
			self.pin = None
			self.appVersion = None
			self.loginChannel = None
			self.authType = None
			self.clientIp = None
			self.uuid = None
			self.mobile = None
			self.open_id_buyer = None
			self.xid_buyer = None

		def getapiname(self):
			return 'jingdong.mfa.userUnifiedAuthentication'

			





