# 架构与日常使用

Windows 客户端负责选择输入、显示检测框、保存结果和调节参数。
选择 Windows 时，图片在电脑本地通过 ONNX Runtime 运行，通常使用 CPU（Central Processing Unit，中央处理器）。选择 R76S 时，客户端把 JPEG 图片通过 HTTP（Hypertext Transfer Protocol，超文本传输协议）发送给板端服务，由 RKNN Lite 驱动 NPU 推理。

```text
图片 / 视频 / 本机摄像头 → Windows 客户端
                           ├─ Windows → ONNX Runtime → 本机结果
                           └─ R76S → HTTP :8765 → RKNN Lite → NPU 结果
R76S USB 摄像头 → /snapshot → 同一板端推理流程 → Windows 显示
```

输入统一为 640×640 RGB（Red Green Blue，红绿蓝）图像，并用黑色补边保持比例。模型有 9 个输出，包含 3 个尺度的检测信息。后处理用 DFL（Distribution Focal Loss，分布焦点损失对应的坐标分布解码）解出检测框，再用 NMS（Non-Maximum Suppression，非极大值抑制）去掉重复框。

浮点 RKNN 用于对照，INT8（8-bit Integer，8 位整数）量化 RKNN 用于板端实际运行。Windows 使用 ONNX，二者不能简单交换文件格式。

## 平时怎么用

只用 Windows：直接打开客户端，选 Windows 或自动，选择输入。无需 R76S。

用已有 R76S：接电、接 LAN 网线，运行网络切换工具，客户端选 R76S。板端服务开机自启，摄像头插在 R76S 上。

同一台已部署设备换电脑：板端不用重装，新电脑只需完整便携客户端和匹配的网络配置。换新 R76S 或重刷系统：按部署说明重新安装。

停止只暂停输入并可能保留最后一帧；刷新画面会停止输入、清空画面和统计。自动模式可以回退，但选择明确的 R76S 模式时需要设备服务在线。

模型类别、尺寸和 SHA256（Secure Hash Algorithm 256-bit，256 位安全散列算法）见 `deploy/model_manifest.json`。哈希用于验证文件内容，不是加密或密码。

既往真机验证：RK3576 驱动 v0.9.8、RKNN Lite 2.3.2；USB 摄像头连续 30 帧测试成功，端到端约 7.09 FPS（Frames Per Second，每秒帧数）。这些是单台设备的历史测试值，不是性能保证。
