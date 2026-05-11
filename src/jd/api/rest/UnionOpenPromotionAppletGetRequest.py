from jd.api.base import RestApi

class UnionOpenPromotionAppletGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.promotionCodeReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.applet.get'

		def get_version(self):
			return '1.0'
			
	

class PromotionCodeReq(object):
		def __init__(self):
			"""
			"""
			self.type = None
			self.subUnionId = None
			self.positionId = None
			self.pid = None
			self.activityType = None





