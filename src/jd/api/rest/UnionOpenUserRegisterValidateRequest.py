from jd.api.base import RestApi

class UnionOpenUserRegisterValidateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.userStateReq = None

		def getapiname(self):
			return 'jd.union.open.user.register.validate'

		def get_version(self):
			return '1.0'
			
	

class UserStateReq(object):
		def __init__(self):
			"""
			"""
			self.userId = None
			self.userIdType = None





