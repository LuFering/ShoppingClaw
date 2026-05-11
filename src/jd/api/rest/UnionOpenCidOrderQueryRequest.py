from jd.api.base import RestApi

class UnionOpenCidOrderQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cidOrderReq = None

		def getapiname(self):
			return 'jd.union.open.cid.order.query'

		def get_version(self):
			return '1.0'
			
	

class CidOrderReq(object):
		def __init__(self):
			"""
			"""
			self.adownerPin = None
			self.type = None
			self.startTime = None
			self.endTime = None
			self.pageIndex = None
			self.pageSize = None





