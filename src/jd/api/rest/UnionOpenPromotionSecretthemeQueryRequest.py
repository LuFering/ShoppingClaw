from jd.api.base import RestApi

class UnionOpenPromotionSecretthemeQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.secretThemeReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.secrettheme.query'

		def get_version(self):
			return '1.0'
			
	

class SecretThemeReq(object):
		def __init__(self):
			"""
			"""
			self.queryType = None





