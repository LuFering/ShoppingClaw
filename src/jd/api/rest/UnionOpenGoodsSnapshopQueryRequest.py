from jd.api.base import RestApi

class UnionOpenGoodsSnapshopQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.SnapShopGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.snapshop.query'

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
			self.sortName = None
			self.sort = None
			self.userIdType = None
			self.userId = None
			self.channelId = None
			self.ip = None
			self.provinceId = None
			self.cityId = None
			self.countryId = None
			self.townId = None





