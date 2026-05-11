from jd.api.base import RestApi

class KplOpenPolcenterUnsubscribeorderRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.factoryId = None
			self.clientIp = None
			self.mobile = None
			self.orderNum = None
			self.imei = None
			self.wifiMac = None
			self.bussName = None
			self.androidId = None

		def getapiname(self):
			return 'jingdong.kpl.open.polcenter.unsubscribeorder'

			





