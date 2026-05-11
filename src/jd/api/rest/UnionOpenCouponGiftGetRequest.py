from jd.api.base import RestApi

class UnionOpenCouponGiftGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.couponReq = None

		def getapiname(self):
			return 'jd.union.open.coupon.gift.get'

		def get_version(self):
			return '1.0'
			
	

class CouponReq(object):
		def __init__(self):
			"""
			"""
			self.skuMaterialId = None
			self.discount = None
			self.amount = None
			self.receiveStartTime = None
			self.receiveEndTime = None
			self.effectiveDays = None
			self.isSpu = None
			self.expireType = None
			self.useStartTime = None
			self.useEndTime = None
			self.share = None
			self.contentMatch = None
			self.couponTitle = None
			self.contentMatchMedias = None
			self.showInMedias = None
			self.targetType = None
			self.childPromoters = None





