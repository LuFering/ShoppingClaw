from jd.api.base import RestApi

class UnionOpenPromotionParseRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.promotionReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.parse'

		def get_version(self):
			return '1.0'
			
	

class PromotionReq(object):
		def __init__(self):
			"""
			"""
			self.promotionUrl = None





