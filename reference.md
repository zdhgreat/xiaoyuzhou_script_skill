# 小宇宙 API 参考

> 此文件按需加载，不占用启动上下文。

## API 端点

### 认证

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/app_auth_tokens.refresh` | GET(Android)/POST(iOS) | 刷新 access_token | refresh_token |
| `/v1/profile/get` | GET | 获取用户信息（验证 token） | access_token |

> 短信登录端点（`/v1/auth/sendCode`）已失效（error 1003），不可用。

### 内容

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/v1/podcast/get?pid=xxx` | GET | 播客详情 | access_token |
| `/v1/episode/list` | POST | 节目列表（分页） | access_token |
| `/v1/episode/get?eid=xxx` | GET | 单集详情（含字幕） | access_token |
| `/v1/private-media/get?eid=xxx` | GET | 付费内容音频 URL | access_token |

## 认证流程

### Token 刷新

```
GET /app_auth_tokens.refresh  (Android 模式)
POST /app_auth_tokens.refresh (iOS 模式)
Headers:
  x-jike-refresh-token: <refresh_token>
  x-jike-device-id: <device_id>
  + 设备指纹头
→ Response Headers 中返回:
  x-jike-access-token: <新 access_token>
  x-jike-refresh-token: <新 refresh_token>
```

**关键**: iOS 模式 token 在响应体中，Android 模式在响应头中。

## 请求头

### Android 模式

```
User-Agent: okhttp/4.12.0
os: android
os-version: 32
manufacturer: vivo
model: V2366GA
applicationid: app.podcast.cosmos
app-version: 2.108.1
app-buildno: 1576
x-jike-device-id: <device_id>
x-jike-access-token: <access_token>
x-jike-device-properties: {"uuid":"...","android_id":"...","oaid":"","vaid":"","aaid":""}
```

### iOS 模式

```
User-Agent: Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)
Market: AppStore
App-BuildNo: 1576
OS: ios
Manufacturer: Apple
BundleID: app.podcast.cosmos
App-Version: 2.57.1
x-jike-device-id: <device_id>
x-jike-access-token: <access_token>
```

## 分页

`/v1/episode/list` 使用 `loadMoreKey` 分页：

```json
// 请求
{"pid": "podcast_id", "limit": 20, "order": "desc"}

// 响应包含 loadMoreKey 时，下一页请求带上:
{"pid": "podcast_id", "limit": 20, "order": "desc", "loadMoreKey": {...}}
```

不再包含 `loadMoreKey` 时表示最后一页。每页建议间隔 0.5 秒。

## 字幕格式

API 返回词级 JSON 数组：

```json
[{"text": "你", "startMs": 1000, "durationMs": 200}, ...]
```

脚本自动按 500ms 间隔分组合成 SRT。

## 付费内容

单集数据中 `isPrivateMedia: true` 表示付费，需额外调用：

```
GET /v1/private-media/get?eid=<episode_id>
→ {"data": {"url": "https://audio-cdn..."}}
```

## 配置文件

路径: `~/.xiaoyuzhou/credentials.json`

```json
{
  "mode": "android",
  "device_id": "...",
  "device_properties": {...},
  "access_token": "...",
  "refresh_token": "...",
  "last_refresh": "2026-05-12 13:55:24"
}
```
