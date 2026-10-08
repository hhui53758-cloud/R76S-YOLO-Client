# 板端 HTTP 接口

默认地址 `http://192.168.137.47:8765`。服务仅面向可信局域网，当前没有账户认证。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | NPU 模型是否就绪 |
| GET | `/status` | 模型、运行时长、请求数量 |
| POST | `/detect` | 上传图像并返回检测结果 |
| GET | `/snapshot?confidence=0.55&iou=0.45` | 拍摄板端摄像头并推理 |
| POST | `/camera/stop` | 释放摄像头 |

`/detect` 的请求体直接放 JPEG 图片字节，使用 `Content-Type: image/jpeg`，不是 multipart 表单。可选请求头 `X-Confidence` 和 `X-Iou`，值均须在 0.01–0.99 范围。图片请求上限为 16 MB。

示例：

```powershell
curl.exe -X POST -H "Content-Type: image/jpeg" -H "X-Confidence: 0.55" --data-binary "@example.jpg" http://192.168.137.47:8765/detect
```

返回 JSON（JavaScript Object Notation，JavaScript 对象表示法），检测项含 `class_id`、`label`、`confidence` 和原图像素坐标 `box: [x1,y1,x2,y2]`。摄像头接口额外返回 `frame_jpeg_base64`。HTTP 400 表示请求无效，500 表示推理或摄像头异常。

`elapsed_ms` 包含服务器记录的推理处理段，并非完整客户端端到端耗时；不要直接把它的倒数当作实际视频帧率。
