from jd.api.base import RestApi

class UnionOpenGoodsHotspotQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.hotspotGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.hotspot.query'

		def get_version(self):
			return '1.0'
			
	

class HotspotGoodsReq(object):
		def __init__(self):
			"""
			"""
			self.contentIds = None





