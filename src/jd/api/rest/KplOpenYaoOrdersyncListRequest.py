from jd.api.base import RestApi

class KplOpenYaoOrdersyncListRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.beginTime = None
			self.endTime = None
			self.state = None

		def getapiname(self):
			return 'jd.kpl.open.yao.ordersync.list'

		def get_version(self):
			return '1.0'
			
	




