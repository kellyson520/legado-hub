# 智能书源健康探测设计

## 目标

让健康诊断页面能够真正触发 Legado 书源的 search → toc → content 探测，并把“未探测”“探测无结论”和“明确失败”区分开；探测过程自动尝试多个关键词，避免单个关键词无结果被误判为未知。

## 方案

1. `SourceProbeService` 对关键词去重后顺序尝试，首个得到搜索结果的关键词进入完整链路；全部无结果时保留每次尝试的摘要。
2. `SourceHealthClassifierService` 将实际探测但无结果/证据不足归为 `degraded`，保留 `keyword_no_result` 或 `unknown_error` 原因；只有没有快照或人工恢复后的状态仍为 `unknown`，并标记 `not_probed`。
3. 健康列表顶部按钮改为批量探测当前页，调用既有批量 API；每个请求使用固定上限，避免一次探测数千个书源。
4. 后台提供有界的健康探测调度入口，沿用现有 Legado 抓取器和持久化探针记录，不改变阅读接口的 search/toc/content 合同。

## 数据流

```text
页面“智能探测本页”
  -> POST /source-health/book-sources/probe-batch
  -> 多关键词 SourceProbeService
  -> LegadoBookSourceFetcher search -> toc -> content
  -> classifier
  -> snapshot + probe_run + book_sources 镜像状态
  -> 页面刷新并显示状态、原因、尝试关键词
```

## 验收标准

- 点击顶部智能探测后产生批量 `POST`，而不是只有列表 `GET`。
- 首次未探测行带有 `not_probed`，不会伪装成已探测未知。
- 第一个关键词无结果、第二个有结果时，最终状态按第二个关键词的完整链路判定。
- 真正无结果或证据不足时显示降级及原因，不再出现无依据的全 unknown。
- 阅读标准书源的 search、目录和正文结果保持兼容，现有健康与阅读测试继续通过。
