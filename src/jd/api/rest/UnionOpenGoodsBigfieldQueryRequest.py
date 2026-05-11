from jd.api.base import RestApi

class UnionOpenGoodsBigfieldQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.bigfield.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReq(object):
		def __init__(self):
			"""
			"""
			self.skuIds = None
			self.fields = None
			self.itemIds = None
			self.sceneId = None





