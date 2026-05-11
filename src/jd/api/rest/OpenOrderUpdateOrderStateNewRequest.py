from jd.api.base import RestApi

class OpenOrderUpdateOrderStateNewRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.orderExtInfo = None
			self.deliverInfo = None

		def getapiname(self):
			return 'jingdong.open.order.updateOrderStateNew'

			
	

class Attribute2(object):
		def __init__(self):
			"""
			"""
			self.manufactureTime = None
			self.validTime = None
			self.batchNum = None
			self.batchCount = None
			self.skuPrice = None


class Attribute1(object):
		def __init__(self):
			"""
			"""
			self.batchList = None
			self.commonName = None
			self.packageSpec = None
			self.manufacturer = None
			self.venderSku = None
			self.skuName = None
			self.skuPlace = None
			self.skuCount = None
			self.approvalNumber = None


class OrderExtInfo(object):
		def __init__(self):
			"""
			"""
			self.orderAmount = None
			self.sendTime = None
			self.skuList = None
			self.orderId = None


class DeliverInfo(object):
		def __init__(self):
			"""
			"""
			self.deliveryId = None
			self.shipmentType = None
			self.logiCompany = None
			self.customerCode = None
			self.logiNo = None





