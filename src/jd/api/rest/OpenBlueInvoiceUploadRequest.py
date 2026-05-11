from jd.api.base import RestApi

class OpenBlueInvoiceUploadRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.orderId = None
			self.invoiceCode = None
			self.invoiceNo = None
			self.invoiceTitle = None
			self.invoiceAmount = None
			self.invoiceDate = None
			self.invoiceImgBase64 = None

		def getapiname(self):
			return 'jingdong.open.blueInvoiceUpload'

			





