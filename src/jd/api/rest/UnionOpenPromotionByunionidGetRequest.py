from jd.api.base import RestApi

class UnionOpenPromotionByunionidGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.promotionCodeReq = None

		def getapiname(self):
			return 'jd.union.open.promotion.byunionid.get'

		def get_version(self):
			return '1.0'
			
	

class PromotionCodeReq(object):
		def __init__(self):
			"""
			"""
			self.materialId = None
			self.unionId = None
			self.positionId = None
			self.pid = None
			self.couponUrl = None
			self.subUnionId = None
			self.chainType = None
			self.giftCouponKey = None
			self.channelId = None
			self.command = None
			self.weChatType = None
			self.rid = None
			self.sceneId = None
			self.proType = None
			self.key = None





