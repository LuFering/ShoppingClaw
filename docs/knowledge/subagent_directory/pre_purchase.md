---
source_type: framework
doc_id: subagent_pre_purchase
category: 子智能体目录
tags: pre_purchase,购前助手,路由,派遣
keywords: pre_purchase,购前助手,派遣,路由,该派谁
title: 购前助手
---

# 购前助手（pre_purchase）

## 能做什么

资深购前决策顾问。负责从需求出发搜索实时商品、整理规格、按硬约束筛选、 做专业取舍并提示风险，最终交付一组可直接展示的推荐候选。 当用户要挑选、对比、比价或询问"值不值得买"时调用。

## 不能做什么

不归档、不下单、不查物流、不做用户画像分析

## 什么情况该派它

- 挑选商品
- 多款对比
- 比价
- 值不值得买
- 找货 / 要推荐

## 交付什么

结构化候选（picks：sku_id / title / price / platform / url）

## 可用工具

- `get_products_specs_extract`
- `filter_products_by_criteria`
- `query_category_knowledge`
- `query_risk_policy`
- `price_calculator`
- `taobao_searchMaterial`
- `taobao_getItemInfo`
- `taobao_convertLink`
- `pdd_goods_search`
- `pdd_goods_detail`
- `pdd_goods_recommend`
- `pdd_goods_prom_url`

## 如何派遣

- 通过 `task` 工具调用，`subagent_type="pre_purchase"`
- 模型：`SenseNova/sensenova-6.8-flash-lite`
