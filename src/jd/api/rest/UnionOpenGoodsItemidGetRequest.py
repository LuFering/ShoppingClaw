from jd.api.base import RestApi

class UnionOpenGoodsItemidGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.itemIdReq = None

		def getapiname(self):
			return 'jd.union.open.goods.itemid.get'

		def get_version(self):
			return '1.0'
			
	

class ItemIdReq(object):
		def __init__(self):
			"""
			"""
			self.skuIds = None





