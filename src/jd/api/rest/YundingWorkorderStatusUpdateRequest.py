from jd.api.base import RestApi

class YundingWorkorderStatusUpdateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.updateWorkOrderStatusVO = None

		def getapiname(self):
			return 'jingdong.yunding.workorder.status.update'

			
	

class UpdateWorkOrderStatusVO(object):
		def __init__(self):
			"""
			"""
			self.repairedTime = None
			self.jobId = None
			self.message = None
			self.status = None





