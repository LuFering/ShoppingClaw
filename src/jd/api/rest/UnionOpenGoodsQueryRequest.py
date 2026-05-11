from jd.api.base import RestApi

class UnionOpenGoodsQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReqDTO = None

		def getapiname(self):
			return 'jd.union.open.goods.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReqDTO(object):
		def __init__(self):
			"""
			"""
			self.cid1 = None
			self.cid2 = None
			self.cid3 = None
			self.pageIndex = None
			self.pageSize = None
			self.skuIds = None
			self.keyword = None
			self.pricefrom = None
			self.priceto = None
			self.commissionShareStart = None
			self.commissionShareEnd = None
			self.owner = None
			self.sortName = None
			self.sort = None
			self.isCoupon = None
			self.isPG = None
			self.pingouPriceStart = None
			self.pingouPriceEnd = None
			self.isHot = None
			self.brandCode = None
			self.shopId = None
			self.hasContent = None
			self.hasBestCoupon = None
			self.pid = None
			self.fields = None
			self.forbidTypes = None
			self.jxFlags = None
			self.shopLevelFrom = None
			self.isbn = None
			self.spuId = None
			self.couponUrl = None
			self.deliveryType = None
			self.eliteType = None
			self.isSeckill = None
			self.isPresale = None
			self.isReserve = None
			self.bonusId = None
			self.area = None
			self.isOversea = None
			self.userIdType = None
			self.userId = None
			self.channelId = None
			self.ip = None
			self.provinceId = None
			self.cityId = None
			self.countryId = None
			self.townId = None
			self.itemIds = None
			self.sceneId = None
			self.searchPosition = None
			self.cPin = None
			self.open_id_buyer = None
			self.xid_buyer = None





