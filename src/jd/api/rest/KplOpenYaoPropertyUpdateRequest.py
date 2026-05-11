from jd.api.base import RestApi

class KplOpenYaoPropertyUpdateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.venderId = None
			self.wareList = None

		def getapiname(self):
			return 'jd.kpl.open.yao.property.update'

		def get_version(self):
			return '1.0'
			
	

class WareListVo(object):
		def __init__(self):
			"""
			"""
			self.venderSku = None
			self.validTime = None





