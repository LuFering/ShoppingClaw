# 京东开放平台SDK API全面分析

## 📊 SDK API总览

SDK中共有 **233个API接口**，分为以下几大类：

---

## 🎯 Research Agent可用API（无需access_token或基础权限）

### ✅ 已集成（5个）

| API方法 | 功能 | 返回数据 | 是否需要token | 适用场景 |
|---------|------|---------|--------------|---------|
| `jingdong.search.ware` | 商品搜索 | SKU ID、标题、图片URL、好评率、店铺ID | ❌ 无需 | 关键词搜索商品列表 |
| `jingdong.ware.productbigfield.get` | 商品大字段详情 | 包装清单、规格参数、商品介绍(HTML) | ❌ 无需 | 获取商品详细规格和描述 |
| `jingdong.new.ware.baseproduct.get` | 商品基础信息 | SKU ID、名称、状态、图片URL、链接 | ❌ 无需 | 批量快速预览商品 |
| `jingdong.ware.productimage.get` | 商品图片查询 | 主图、详情图列表（最多10张） | ❌ 无需 | 批量获取商品图片 |
| `jingdong.new.ware.mobilebigfield.get` | 移动端详情 | HTML富文本详情内容 | ❌ 无需 | 获取移动端商品详情 |

### ⚠️ 待实现（0个）

**测试结果（2026-05-05）**：以下API均需要access_token，暂时无法集成：
- ❌ `biz.product.commentSummarys.query` - 评论摘要查询（需要token）
- ❌ `biz.product.state.query` - 商品状态查询（需要token）
- ❌ `jd.biz.product.getSimilarSku` - 同款商品查询（需要token）

### 🔍 潜在可用（需测试）

| API方法 | 功能 | 返回数据 | 是否需要token | 备注 |
|---------|------|---------|--------------|------|
| `biz.product.skuImage.query` | SKU图片查询 | SKU级别图片 | ❌ 无需 | 可能与productimage重复 |
| `new.ware.productsafedays.get` | 商品保质期 | 保质期天数 | ❌ 无需 | 仅食品类有用 |
| `ware.basebook.get` | 图书基础信息 | ISBN、作者、出版社 | ❌ 无需 | 仅图书类有用 |
| `ware.bookbigfield.get` | 图书大字段 | 目录、简介 | ❌ 无需 | 仅图书类有用 |

---

## ❌ 不可用API（需要access_token或特殊权限）

### 🔒 价格相关（需要access_token）

| API方法 | 功能 | 返回数据 | 权限要求 |
|---------|------|---------|---------|
| `biz.price.sell_price.get` | 售价查询 | 当前售价、促销价 | access_token |
| `kpl.open.getsellprice.query` | 开普勒售价 | 销售价格 | access_token |
| `kepler.yao.ware.price.update` | 商品价格更新 | - | 商家端+token |
| `kpl.open.yao.multiprice.update` | 多价格更新 | - | 商家端+token |

### 🔒 库存相关（需要access_token）

| API方法 | 功能 | 返回数据 | 权限要求 |
|---------|------|---------|---------|
| `kpl.open.getnewstockbyid.query` | 库存查询 | 库存数量、状态 | access_token |
| `kepler.yao.ware.stock.update` | 库存更新 | - | 商家端+token |
| `stock.for.list.batget` | 批量库存查询 | 库存列表 | access_token |
| `stock.open.api.update.vender.stock.num` | 商家库存更新 | - | 商家端+token |

### 🔒 订单相关（需要access_token + 用户授权）

| API方法 | 功能 | 返回数据 | 权限要求 |
|---------|------|---------|---------|
| `order.jd.order.query` | 订单查询 | 订单详情 | access_token + 用户授权 |
| `open.order.getorderlist` | 订单列表 | 订单列表 | access_token + 用户授权 |
| `order.order.track.query` | 物流追踪 | 物流信息 | access_token |
| `kpl.open.polcenter.subscribeorder` | 订单订阅 | - | access_token |

### 🔒 联盟推广相关（需要联盟权限 + access_token）

| API方法 | 功能 | 返回数据 | 权限要求 |
|---------|------|---------|---------|
| `jd.union.open.goods.query` | 商品详情查询 | SKU、价格、佣金、优惠券 | 联盟权限+token |
| `jd.union.open.goods.bigfield.query` | 商品大字段 | 图文详情、规格 | 联盟权限+token |
| `jd.union.open.goods.jingfen.query` | 京粉精选 | 高佣商品列表 | 联盟权限+token |
| `jd.union.open.goods.rank.query` | 商品排行榜 | 热销/新品排行 | 联盟权限+token |
| `jd.union.open.goods.promotiongoodsinfo.query` | 促销商品信息 | 促销价、优惠券 | 联盟权限+token |
| `jd.union.open.coupon.query` | 优惠券查询 | 优惠券信息 | 联盟权限+token |
| `jd.union.open.promotion.common.get` | 推广链接生成 | 推广链接 | 联盟权限+token |

### 🔒 商家端API（需要商家资质）

| API方法 | 功能 | 返回数据 | 权限要求 |
|---------|------|---------|---------|
| `kpl.open.wfp.jmiware.add.ware` | 添加商品 | - | 商家端 |
| `kpl.open.wfp.jmiware.edit.ware` | 编辑商品 | - | 商家端 |
| `kpl.open.wfp.jmiware.update.ware.status` | 更新商品状态 | - | 商家端 |
| `after.sale.afs.apply.create` | 售后申请 | - | 商家端 |
| `invoice.submit` | 发票提交 | - | 商家端 |

### 🔒 其他需要权限的API

| API方法 | 功能 | 权限要求 |
|---------|------|---------|
| `mfa.user.unified.authentication` | 用户认证 | OAuth2.0 |
| `user.get.user.info.by.open.id` | 用户信息查询 | 用户授权 |
| `detection.images.red.line.detect.batch` | 图片违规检测 | 特殊权限 |
| `imgzone.picture.upload` | 图片上传 | 商家端 |

---

## 📋 API分类总结

### 按业务领域分类

#### 1. 商品查询类（15个）
- ✅ `jingdong.search.ware` - 商品搜索
- ✅ `jingdong.ware.productbigfield.get` - 商品大字段
- ✅ `jingdong.new.ware.baseproduct.get` - 基础信息
- ✅ `jingdong.ware.productimage.get` - 商品图片
- ✅ `jingdong.new.ware.mobilebigfield.get` - 移动端详情
- ⚠️ `biz.product.commentSummarys.query` - 评论摘要
- ⚠️ `biz.product.state.query` - 商品状态
- ⚠️ `jd.biz.product.getSimilarSku` - 同款商品
- ⚠️ `biz.product.skuImage.query` - SKU图片
- ⚠️ `new.ware.productsafedays.get` - 保质期
- ❌ `union.open.goods.query` - 联盟商品详情
- ❌ `union.open.goods.bigfield.query` - 联盟大字段
- ❌ `union.open.goods.jingfen.query` - 京粉精选
- ❌ `union.open.goods.rank.query` - 商品排行
- ❌ `union.open.goods.promotiongoodsinfo.query` - 促销信息

#### 2. 价格库存类（8个）
- ❌ `biz.price.sell_price.get` - 售价查询
- ❌ `kpl.open.getsellprice.query` - 开普勒售价
- ❌ `kpl.open.getnewstockbyid.query` - 库存查询
- ❌ `stock.for.list.batget` - 批量库存
- ❌ `kepler.yao.ware.price.update` - 价格更新（商家）
- ❌ `kepler.yao.ware.stock.update` - 库存更新（商家）
- ❌ `kpl.open.yao.multiprice.update` - 多价格更新
- ❌ `stock.open.api.update.vender.stock.num` - 商家库存

#### 3. 订单物流类（12个）
- ❌ `order.jd.order.query` - 订单查询
- ❌ `open.order.getorderlist` - 订单列表
- ❌ `order.order.track.query` - 物流追踪
- ❌ `order.freight.get` - 运费查询
- ❌ `order.waybilltrack.search` - 运单追踪
- ❌ `kpl.open.polcenter.subscribeorder` - 订单订阅
- ❌ `kpl.open.polcenter.getexpressinfo` - 快递信息
- ❌ `yjc.fgc.get.order.detail` - 订单详情
- ❌ `yjc.fgc.get.order.list` - 订单列表
- ❌ `trade.dqg.plan.list.query` - 定期购计划
- ❌ `kpl.open.regular.plan.queryplanlistnew` - 定期购列表
- ❌ `kpl.open.selectjdorder.query` - 选择订单

#### 4. 联盟推广类（40+个）
- ❌ `union.open.goods.*` - 商品相关（10+个）
- ❌ `union.open.promotion.*` - 推广相关（8个）
- ❌ `union.open.coupon.*` - 优惠券相关（3个）
- ❌ `union.open.order.*` - 订单相关（5个）
- ❌ `union.open.statistics.*` - 统计相关（6个）
- ❌ `union.open.activity.*` - 活动相关（3个）
- ❌ `union.open.channel.*` - 渠道相关（4个）
- ❌ `union.open.position.*` - 位置相关（2个）
- ❌ `union.open.exchange.*` - 换货相关（7个）

#### 5. 售后服务类（8个）
- ❌ `after.sale.afs.apply.create` - 售后申请
- ❌ `after.sale.service.detail.info.query` - 售后详情
- ❌ `after.sale.service.list.page.query` - 售后列表
- ❌ `after.sale.audit.cancel.query` - 审核取消
- ❌ `after.sale.available.number.comp.query` - 可用数量
- ❌ `after.sale.customer.expect.comp.query` - 客户期望
- ❌ `after.sale.send.sku.update` - 寄回SKU
- ❌ `after.sale.ware.return.jd.comp.query` - 退回京东

#### 6. 地址发票类（10个）
- ⚠️ `address.all.provinces.query` - 省份查询
- ⚠️ `address.citys.by.province.id.query` - 城市查询
- ⚠️ `address.countys.by.city.id.query` - 区县查询
- ⚠️ `address.towns.by.county.id.query` - 乡镇查询
- ❌ `invoice.query` - 发票查询
- ❌ `invoice.submit` - 发票提交
- ❌ `invoice.waybill` - 发票运单
- ❌ `open.blue.invoice.upload` - 蓝票上传
- ❌ `open.red.invoice.upload` - 红票上传
- ❌ `kpl.open.invoice.querythrapplyno` - 发票查询

#### 7. 用户认证类（5个）
- ❌ `mfa.user.unified.authentication` - 统一认证
- ❌ `mfa.inner.user.unified.authentication` - 内部认证
- ❌ `user.get.user.info.by.open.id` - 用户信息
- ❌ `jos.master.key.get` - 主密钥
- ❌ `jos.secret.api.report.get` - 秘钥报告

#### 8. 其他工具类（10个）
- ⚠️ `ware.basebook.get` - 图书信息
- ⚠️ `ware.bookbigfield.get` - 图书大字段
- ❌ `detection.images.red.line.detect.batch` - 图片检测
- ❌ `imgzone.picture.upload` - 图片上传
- ❌ `h5.open.mini.get.mini.program.scheme` - 小程序scheme
- ❌ `jsf.xb.xb.product.service.query.products` - 产品服务
- ❌ `kepler.settled.address.getareabymehodname` - 地区查询
- ❌ `kepler.sku.product.service` - SKU服务
- ❌ `pop.order.encrypt.mobile.num` - 加密手机号
- ❌ `pop.order.getmobilelist` - 手机号列表

---

## 🎯 Research Agent推荐集成方案

### 第一阶段：核心功能（已完成✅）
1. ✅ `jingdong.search.ware` - 商品搜索
2. ✅ `jingdong.ware.productbigfield.get` - 商品详情
3. ✅ `jingdong.new.ware.baseproduct.get` - 基础信息
4. ✅ `jingdong.ware.productimage.get` - 商品图片
5. ✅ `jingdong.new.ware.mobilebigfield.get` - 移动端详情

### 第二阶段：增强功能（需要access_token⚠️）

**以下API经测试均需要access_token，暂时无法集成：**

6. ❌ `biz.product.commentSummarys.query` - **评论摘要**
   - 返回：好评数、总评数、评分、好评率
   - 价值：帮助用户判断商品质量
   - 状态：❌ 需要access_token

7. ❌ `biz.product.state.query` - **商品状态**
   - 返回：上下架状态、库存状态
   - 价值：避免推荐下架商品
   - 状态：❌ 需要access_token

8. ❌ `jd.biz.product.getSimilarSku` - **同款商品**
   - 返回：同款SKU列表
   - 价值：提供更多选择
   - 状态：❌ 需要access_token

### 第三阶段：扩展功能（可选）
9. ⚠️ `new.ware.productsafedays.get` - 保质期（仅食品类）
10. ⚠️ `ware.basebook.get` - 图书信息（仅图书类）
11. ⚠️ `ware.bookbigfield.get` - 图书详情（仅图书类）

### ❌ 不建议集成
- 所有需要access_token的API（价格、库存、订单）
- 所有联盟推广API（需要联盟权限）
- 所有商家端API（需要商家资质）
- 所有用户授权API（需要OAuth2.0）

---

## 📊 数据统计

| 类别 | 总数 | 可用(无需token) | 需token | 需特殊权限 |
|------|------|----------------|---------|-----------|
| 商品查询 | 15 | **5** | 3 | 7 |
| 价格库存 | 8 | 0 | 8 | 0 |
| 订单物流 | 12 | 0 | 12 | 0 |
| 联盟推广 | 40+ | 0 | 0 | 40+ |
| 售后服务 | 8 | 0 | 8 | 0 |
| 地址发票 | 10 | 4 | 6 | 0 |
| 用户认证 | 5 | 0 | 5 | 0 |
| 其他工具 | 10 | 3 | 7 | 0 |
| **总计** | **~108** | **12** | **49** | **47** |

**可用率：12/108 ≈ 11%**

---

## 💡 结论与建议

### 现状
- SDK共233个API，但**Research Agent可用的仅5个（4.6%）**
- 大部分API需要access_token或特殊权限
- 价格、库存、订单、评论等核心电商数据均需要授权

### 优势
- 已有的5个API覆盖了**搜索、详情、图片、基础信息、移动端详情**
- 无需access_token，部署简单
- 符合“消费者视角”定位

### 不足
- **缺少价格查询功能**（所有价格API都需要token）
- **缺少评论数据**（影响购买决策，评论API需要token）
- **缺少库存状态**（可能推荐下架商品，状态API需要token）
- **缺少同款推荐**（同款API需要token）

### 建议
1. **当前策略**：保持现有5个API，满足基本需求
2. **备选方案**：从HTML中解析价格和评论数据（使用`jd_product_mobile_detail`）
3. **长期规划**：申请access_token以启用更多功能
4. **不推荐**：集成联盟API（需要企业资质+联盟权限）
