from jd.api.base import RestApi

class UnionOpenShPromotionGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.getCodeByTaskIdReq = None

		def getapiname(self):
			return 'jd.union.open.sh.promotion.get'

		def get_version(self):
			return '1.0'
			
	

class GetCodeByTaskIdReq(object):
		def __init__(self):
			"""
			"""
			self.account = None
			self.materialId = None
			self.taskId = None
			self.ext1 = None
			self.pid = None
			self.couponUrl = None
			self.giftCouponKey = None
			self.channelId = None
			self.sceneId = None





