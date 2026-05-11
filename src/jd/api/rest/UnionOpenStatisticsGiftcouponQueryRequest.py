from jd.api.base import RestApi

class UnionOpenStatisticsGiftcouponQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.effectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.giftcoupon.query'

		def get_version(self):
			return '1.0'
			
	

class EffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.skuId = None
			self.giftCouponKey = None
			self.createTime = None
			self.startTime = None
			self.key = None
			self.targetType = None
			self.itemId = None





