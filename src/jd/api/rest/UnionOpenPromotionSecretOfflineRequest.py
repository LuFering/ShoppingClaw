from jd.api.base import RestApi

class UnionOpenPromotionSecretOfflineRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.secretOfflineReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.secret.offline'

		def get_version(self):
			return '1.0'
			
	

class SecretOfflineReq(object):
		def __init__(self):
			"""
			"""
			self.secretIds = None





