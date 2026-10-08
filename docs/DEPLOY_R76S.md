# 从零部署 R76S

## 1. 安装板端系统

使用 FriendlyElec 面向 NanoPi R76S/RK3576 的 Ubuntu 镜像。核对设备型号与镜像用途：SD-to-eMMC 镜像会把系统写入板载 eMMC（embedded MultiMediaCard，嵌入式多媒体存储卡），会覆盖其原有系统。

备份设备数据后，按厂家文档把正确镜像写入 TF/microSD 卡，断电插卡安装，完成后断电拔卡重新启动。本项目不附带系统镜像，避免把大型且版本相关的固件混入源码。

## 2. 网络与 SSH

SSH（Secure Shell，安全外壳协议）用于远程登录板端。新系统的账户和密码请以对应镜像说明为准，不要把默认密码写入公共仓库。

先把 R76S 接到路由器分配地址，或使用电脑共享网络。确认实际 IP 后，在 PowerShell 中：

```powershell
ssh pi@BOARD_IP
```

首次连接请核对设备指纹。直连场景可以把板端固定为 `192.168.137.47/24`，电脑设为 `192.168.137.1/24`。固定网络前先检查 `nmcli connection show`，不要把其他电脑或设备的连接名称直接照搬。

## 3. 传输与依赖

把仓库的 `deploy` 目录传到板端，例如：

```powershell
scp -r deploy pi@BOARD_IP:~/r76s-yolo/
```

板端应能导入 OpenCV/NumPy，并提供 RKNPU 驱动和 `librknnrt.so`。Ubuntu 用户空间安装本身不会补齐缺失的 NPU 内核驱动。

从 [Rockchip 官方 RKNN Toolkit2](https://github.com/airockchip/rknn-toolkit2/tree/master/rknn-toolkit-lite2/packages) 下载 RKNN Toolkit Lite2 2.3.2 的 ARM64 wheel；按板端 Python 版本选择 `cp312`（Python 3.12）或相应版本。wheel 是 Python 的二进制安装包，不适用于任意架构。

把 wheel 放到板端，然后在板端普通用户终端运行：

```bash
cd ~/r76s-yolo/deploy
bash setup_board.sh /path/to/rknn_toolkit_lite2-2.3.2-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
venv/bin/python r76s_http_service.py --bind 0.0.0.0 --port 8765
```

在另一终端查看健康状态：

```bash
curl http://127.0.0.1:8765/health
```

确认成功后停止前台进程，安装开机服务：

```bash
bash install_http_service.sh
systemctl status r76s-yolo-http.service
journalctl -u r76s-yolo-http.service -n 50
```

安装脚本会按实际用户和目录生成服务单元，并停用同名旧常驻摄像头服务，避免摄像头占用。附带的 `.service` 文件只是默认 `pi` 布局示例，应以安装脚本生成结果为准。

## 4. 摄像头与客户端

摄像头插入 R76S，确认 `/dev/video0` 存在、板端用户属于 `video` 和 `render` 用户组。健康检查成功不代表摄像头已连接。摄像头接口默认采集 MJPG 1280×720，可依实际硬件调整源码。

在 Windows 客户端选择 R76S，打开测试图片或点击 R76S 摄像头。

HTTP 服务没有认证和 TLS（Transport Layer Security，传输层安全协议），只适合可信局域网。不要把 8765 端口映射到公网。

## 5. 更换或重新转换模型

本项目附带可以运行的 3 份模型，完整训练集和训练工程不在仓库中。使用自己的模型需要保证四类顺序和 9 输出结构一致。

模型转换在桌面 Linux/WSL（Windows Subsystem for Linux，适用于 Linux 的 Windows 子系统）中完成，不在 Windows 客户端的依赖环境中完成。使用 Rockchip 的 `ultralytics_yolo11` 导出器和 RKNN Toolkit2 2.3.2；芯片目标必须为 `rk3576`。INT8 校准应使用具备授权且具有代表性的训练图片；历史模型使用 200 张图片校准，但仓库不附这些图片。

更新模型后同步 `model_manifest.json` 和 `SHA256SUMS.txt`，分别验证 Windows 与板端结果。不能把普通单输出 YOLO ONNX 直接替换进本项目。
