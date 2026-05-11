from jd.api.base import RestApi

class KplOpenRegularPlanShipmentorderRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.shipmentParam = None

		def getapiname(self):
			return 'jd.kpl.open.regular.plan.shipmentorder'

		def get_version(self):
			return '1.0'
			
	

class ShipmentParam(object):
		def __init__(self):
			"""
			"""
			self.venderId = None
			self.planId = None
			self.orderId = None
			self.logiCoprId = None
			self.logiNo = None
			self.installId = None





