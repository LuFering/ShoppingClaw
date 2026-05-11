from jd.api.base import RestApi

class UnionOpenExchangeMediaTaskQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.taskInfoQueryReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.task.query'

		def get_version(self):
			return '1.0'
			
	

class TaskInfoQueryReq(object):
		def __init__(self):
			"""
			"""
			self.taskId = None
			self.taskCode = None
			self.uuid = None





