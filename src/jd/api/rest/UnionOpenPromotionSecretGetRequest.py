from jd.api.base import RestApi

class UnionOpenPromotionSecretGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.secretReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.secret.get'

		def get_version(self):
			return '1.0'
			
	

class SecretReq(object):
		def __init__(self):
			"""
			"""
			self.secretThemeId = None
			self.secretKeyWord = None
			self.tu = None
			self.tuName = None
			self.webId = None
			self.effectiveStartTime = None
			self.effectiveEndTime = None
			self.channelId = None
			self.subUnionId = None
			self.promotionType = None
			self.positionId = None
			self.pid = None





