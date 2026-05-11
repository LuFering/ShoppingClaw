from jd.api.base import RestApi

class UnionOpenGoodsJingfenQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.jingfen.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReq(object):
		def __init__(self):
			"""
			"""
			self.eliteId = None
			self.pageIndex = None
			self.pageSize = None
			self.sortName = None
			self.sort = None
			self.pid = None
			self.fields = None
			self.forbidTypes = None
			self.groupId = None
			self.ownerUnionId = None
			self.timeType = None
			self.userIdType = None
			self.userId = None
			self.channelId = None
			self.ip = None
			self.provinceId = None
			self.cityId = None
			self.countryId = None
			self.townId = None
			self.cPin = None
			self.open_id_buyer = None
			self.xid_buyer = None





