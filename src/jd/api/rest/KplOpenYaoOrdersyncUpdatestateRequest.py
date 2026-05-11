from jd.api.base import RestApi

class KplOpenYaoOrdersyncUpdatestateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.orderId = None
			self.deliverInfo = None

		def getapiname(self):
			return 'jd.kpl.open.yao.ordersync.updatestate'

		def get_version(self):
			return '1.0'
			
	

class DeliverInfo(object):
		def __init__(self):
			"""
			"""
			self.shipmentType = None
			self.customerCode = None
			self.deliveryId = None
			self.logiNo = None
			self.logiCompany = None





