from jd.api.base import RestApi

class KplOpenSkuQueryinfoRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.skuQuery = None

		def getapiname(self):
			return 'jd.kpl.open.sku.queryinfo'

		def get_version(self):
			return '1.0'
			
	

class SkuQuery(object):
		def __init__(self):
			"""
			"""
			self.venderId = None
			self.skuAlias = None
			self.pageSize = None
			self.currentPage = None
			self.wareState = None





