from jd.api.base import RestApi

class UnionOpenPromotionSecretQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.secretQueryReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.secret.query'

		def get_version(self):
			return '1.0'
			
	

class SecretQueryReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.id = None
			self.applyStartTime = None
			self.applyEndTime = None
			self.secretThemeId = None
			self.secretKeyWord = None
			self.status = None
			self.channelId = None





