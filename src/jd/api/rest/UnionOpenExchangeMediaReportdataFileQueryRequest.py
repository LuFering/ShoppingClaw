from jd.api.base import RestApi

class UnionOpenExchangeMediaReportdataFileQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.reportDataFileQueryReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.reportdata.file.query'

		def get_version(self):
			return '1.0'
			
	

class ReportDataFileQueryReq(object):
		def __init__(self):
			"""
			"""
			self.ossFileDataType = None
			self.activeDate = None
			self.uuid = None





