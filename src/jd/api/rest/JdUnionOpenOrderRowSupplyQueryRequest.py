from jd.api.base import RestApi

class JdUnionOpenOrderRowSupplyQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.orderReq = None

		def getapiname(self):
			return 'jd.jd.union.open.order.row.supply.query'

		def get_version(self):
			return '1.0'
			
	

class OrderReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.type = None
			self.startTime = None
			self.endTime = None
			self.fields = None
			self.orderId = None





