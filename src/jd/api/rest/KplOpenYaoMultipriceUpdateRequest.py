from jd.api.base import RestApi

class KplOpenYaoMultipriceUpdateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.list = None

		def getapiname(self):
			return 'jd.kpl.open.yao.multiprice.update'

		def get_version(self):
			return '1.0'
			
	

class PriceName(object):
		def __init__(self):
			"""
			"""
			self.price = None
			self.priceNameEnum = None


class ListVo(object):
		def __init__(self):
			"""
			"""
			self.venderSku = None
			self.priceNames = None





