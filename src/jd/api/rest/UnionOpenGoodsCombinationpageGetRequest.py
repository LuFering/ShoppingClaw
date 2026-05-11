from jd.api.base import RestApi

class UnionOpenGoodsCombinationpageGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.combinationGoodsPageReq = None

		def getapiname(self):
			return 'jd.union.open.goods.combinationpage.get'

		def get_version(self):
			return '1.0'
			
	

class CombinationGoodsPageReq(object):
		def __init__(self):
			"""
			"""
			self.skuInfo = None
			self.couponUrls = None
			self.activityUrls = None





