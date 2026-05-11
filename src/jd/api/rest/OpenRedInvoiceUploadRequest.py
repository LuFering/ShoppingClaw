from jd.api.base import RestApi

class OpenRedInvoiceUploadRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.invoiceDate = None
			self.invoiceCode = None
			self.invoiceAmount = None
			self.blueInvoiceCode = None
			self.orderId = None
			self.invoiceNo = None
			self.invoiceTitle = None
			self.blueInvoiceNo = None
			self.invoiceImgBase64 = None

		def getapiname(self):
			return 'jingdong.open.redInvoiceUpload'

			





