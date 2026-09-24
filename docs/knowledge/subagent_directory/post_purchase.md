---
source_type: framework
doc_id: subagent_post_purchase
category: 子智能体目录
tags: post_purchase,购后助手,路由,派遣
keywords: post_purchase,购后助手,派遣,路由,该派谁
title: 购后助手
---

# 购后助手（post_purchase）

## 能做什么

资深用户洞察与购物档案专家。负责构建立体用户画像、推进购物阶段、 设置提醒并做使用复盘，为当前决策提炼真正有指导价值的个性化参数。 当需要了解用户偏好、个性化推荐、或记录本次对话产生的新偏好时调用。

## 不能做什么

不搜新商品、不做商品对比、不出推荐卡、不评价商品；不碰订单 / 物流 / 售后 / 支付

## 什么情况该派它

- 已决定购买 / 已下单 / 已收货
- 表达可长期复用的偏好（品牌、预算、使用场景）
- 要求提醒（比价、降价、保修到期、收货确认）
- 想先记下来 / 以后再说
- 要写使用反馈或复盘

## 交付什么

购物档案条目（归档 / 阶段推进 / 提醒 / 复盘）

## 可用工具

- `get_user_shopping_context`
- `save_user_preference`
- `recall_past_decisions`
- `get_user_profile`
- `save_to_archive`
- `update_record_phase`
- `set_reminder`
- `write_review`

## 如何派遣

- 通过 `task` 工具调用，`subagent_type="post_purchase"`
- 模型：`SenseNova/sensenova-6.8-flash-lite`
