from jd.api.base import RestApi

class StockOpenApiUpdateVenderStockNumRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderStockParam = None
			self.callerParam = None

		def getapiname(self):
			return 'jingdong.stock.open.api.updateVenderStockNum'

			
	

class VenderStockDetailParam(object):
		def __init__(self):
			"""
			"""
			self.num = None
			self.skuId = None
			self.sid = None


class VenderStockParam(object):
		def __init__(self):
			"""
			"""
			self.companyId = None
			self.venderStockDetailParamList = None
			self.venderCode = None
			self.billId = None
			self.extBillId = None
			self.extParamMap = None


class CallerParam(object):
		def __init__(self):
			"""
			"""
			self.systemName = None
			self.sysIp = None





