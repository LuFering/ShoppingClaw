from jd.api.base import RestApi

class UnionOpenGoodsHotspotContentQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.hotspotContentReq = None

		def getapiname(self):
			return 'jd.union.open.goods.hotspot.content.query'

		def get_version(self):
			return '1.0'
			
	

class HotspotContentReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.startTime = None
			self.endTime = None
			self.type = None





