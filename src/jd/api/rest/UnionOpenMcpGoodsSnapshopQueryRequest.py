from jd.api.base import RestApi

class UnionOpenMcpGoodsSnapshopQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.snapShopGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.mcp.goods.snapshop.query'

		def get_version(self):
			return '1.0'
			
	

class SnapShopGoodsReq(object):
		def __init__(self):
			"""
			"""
			self.imageData = None
			self.imageId = None
			self.pageIndex = None
			self.pageSize = None
			self.userIdType = None
			self.userId = None
			self.channelId = None





