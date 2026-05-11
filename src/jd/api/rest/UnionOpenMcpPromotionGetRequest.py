from jd.api.base import RestApi

class UnionOpenMcpPromotionGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.promotionCodeReq = None

		def getapiname(self):
			return 'jd.union.open.mcp.promotion.get'

		def get_version(self):
			return '1.0'
			
	

class PromotionCodeReq(object):
		def __init__(self):
			"""
			"""
			self.materialId = None
			self.couponUrl = None
			self.channelId = None
			self.openId = None





