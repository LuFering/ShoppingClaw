from jd.api.base import RestApi

class JsfXbXBProductServiceQueryProductsRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.startRow = None
			self.limitCnt = None

		def getapiname(self):
			return 'jingdong.jsf.xb.XBProductService.queryProducts'

			





