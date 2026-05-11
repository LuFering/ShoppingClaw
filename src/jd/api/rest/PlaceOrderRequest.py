from jd.api.base import RestApi

class PlaceOrderRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.param1 = None

		def getapiname(self):
			return 'jingdong.placeOrder'

			
	

class Attribute1(object):
		def __init__(self):
			"""
			"""
			self.goodsNo = None
			self.lotAttrMap = None
			self.goodsName = None
			self.seq = None


class Attribute2(object):
		def __init__(self):
			"""
			"""
			self.goodsNoParam = None
			self.skuTotalAmount = None
			self.seqNo = None
			self.qty = None
			self.isbn = None
			self.priceType = None
			self.salePrimePrice = None
			self.serialFlag = None
			self.saleDiscount = None
			self.saleActualPrice = None
			self.type = None
			self.goodsNameParam = None


class OrderParam(object):
		def __init__(self):
			"""
			"""
			self.orderType = None
			self.customRemark = None
			self.saleId = None
			self.jdOrderNo = None
			self.totalPrice = None
			self.sellerNo = None
			self.discountAmount = None
			self.saleName = None
			self.goodsSeqsList = None
			self.jdStatus = None
			self.projectNo = None
			self.siteNo = None
			self.pinParam = None
			self.totalPriceValue = None
			self.offLineOrder = None
			self.orderSource = None
			self.customTel = None
			self.actualAmount = None
			self.customName = None
			self.cashPayWay = None
			self.cartGoodsInfoList = None
			self.totalDiscount = None
			self.payStatus = None
			self.open_id_seller = None
			self.xid_seller = None


class Param1(object):
		def __init__(self):
			"""
			"""
			self.orderParam = None
			self.venderId = None
			self.source = None





