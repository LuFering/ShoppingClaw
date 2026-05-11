from jd.api.base import RestApi

class UnionOpenStatisticsPromotionQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.promotionEffectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.promotion.query'

		def get_version(self):
			return '1.0'
			
	

class PromotionEffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.skuId = None
			self.activityUrl = None
			self.timeType = None
			self.dataType = None
			self.fields = None
			self.itemId = None





