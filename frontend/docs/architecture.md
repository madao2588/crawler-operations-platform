# Flutter 前端架构设计

## 一、产品定位

该前端面向需要持续采集、筛选和复核网页信息的业务团队。

它不是通用爬虫后台，而是一个业务监测与情报审阅系统，核心目标是帮助用户：
- 快速发现相关招标公告
- 根据关键词筛选有效信息
- 查看标题、发布时间、正文和来源
- 一键跳转到原始公告页面
- 管理监测规则与来源网站

## 二、平台策略

优先目标平台：
- Flutter Web

后续兼容平台：
- Windows Desktop
- macOS Desktop

当前不作为第一优先级：
- 移动端完整适配

## 三、架构原则

- 业务优先，系统配置次之
- 按功能模块划分目录，而不是按技术类型堆叠
- 页面层、应用层、领域层、数据层职责清晰
- 与现有 FastAPI 后端通过 HTTP API 集成
- 优先保证页面结构清楚、组件可复用、后续可扩展

## 四、推荐分层

### 1. Presentation 层

职责：
- 页面
- 布局
- 组件
- 视图状态
- 用户交互

示例：
- 首页看板
- 公告中心
- 公告详情抽屉
- 来源网站列表页

### 2. Application 层

职责：
- 串联页面需求与业务动作
- 处理刷新、查询、分页、筛选等流程
- 为界面提供可直接消费的数据结构

示例：
- 加载首页看板数据
- 根据关键词和时间查询公告
- 标记公告为重点

### 3. Domain 层

职责：
- 定义业务实体
- 定义用例接口
- 沉淀业务语义

核心实体建议：
- Notice
- KeywordRule
- SourceSite
- MonitoringTask
- SystemLog

### 4. Data 层

职责：
- API Client
- DTO 映射
- Repository 实现

数据来源：
- FastAPI 后端接口

## 五、目录规划

```text
frontend/lib/
├── app/
│   ├── app.dart
│   ├── navigation/
│   └── router/
├── core/
│   ├── config/
│   ├── constants/
│   ├── network/
│   ├── theme/
│   └── utils/
├── features/
│   ├── dashboard/
│   ├── notices/
│   ├── keyword_rules/
│   ├── source_sites/
│   └── system_management/
├── shared/
│   ├── enums/
│   ├── models/
│   └── widgets/
└── main.dart
```

## 六、功能模块

### Dashboard

目标：
- 展示今日公告概览
- 展示高价值公告
- 展示关键词热度
- 展示来源网站分布

### Notices

目标：
- 作为主工作台使用
- 快速筛选、查看、跳转原文

### Keyword Rules

目标：
- 管理监测关键词
- 管理关键词优先级和分组

### Source Sites

目标：
- 管理监测的网站与栏目
- 查看抓取方式、状态、最近执行情况

### System Management

目标：
- 提供管理员视角
- 查看任务、日志、异常和调度状态

## 七、导航策略

一级导航建议：
- 首页看板
- 公告中心
- 关键词规则
- 来源网站
- 系统管理

桌面端布局建议：
- 左侧固定导航
- 顶部状态栏
- 右侧内容区

## 八、后端对接原则

现有后端接口命名偏技术化，前端展示时建议转成业务文案：

- tasks -> 监测任务
- collected_data -> 公告数据
- logs -> 运行日志

第一阶段优先使用的接口：
- `GET /v1/dashboard/overview`
- `GET /v1/notices`
- `GET /v1/notices/{id}`
- `GET /v1/notices/{id}/snapshot`
- `GET /v1/tasks`
- `POST /v1/tasks/{id}/run`
- `GET /v1/logs`

## 九、第一阶段里程碑

建议先完成：
- 首页看板
- 公告中心
- 公告详情区
- 关键词规则页
- 来源网站页

系统管理页可在业务主链路清晰后继续补强。
