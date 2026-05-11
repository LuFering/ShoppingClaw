from jd.api.base import RestApi

class KplOpenYaoShelfstateBatchupdateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.wareList = None

		def getapiname(self):
			return 'jd.kpl.open.yao.shelfstate.batchupdate'

		def get_version(self):
			return '1.0'
			
	

class WareListVo(object):
		def __init__(self):
			"""
			"""
			self.venderSku = None
			self.status = None
			self.skuStock = None
			self.skuPrice = None
			self.validTime = None





