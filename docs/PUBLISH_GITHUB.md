# 上传 GitHub 与发布

## 上传哪个目录

只上传本仓库目录。不要上传父级目录或旧 `R76S` 工作目录；那里可能包含设备私钥、训练数据、个人照片和系统镜像。

项目源代码、说明和模型提交到仓库；生成的 `release/*.zip` 作为 Releases 附件上传，不放入源码历史。当前三份模型合计约 27 MB，频繁更新大模型时建议再配置 Git LFS（Large File Storage，大文件存储）或改用 Release 分发。

## 推荐：GitHub Desktop

1. 在 GitHub 新建一个空仓库，不提前添加 README 或许可证。
2. GitHub Desktop 选择 Add local repository，选本项目目录。
3. 核对 Changes 没有私钥、日志、虚拟环境、照片或安装包。
4. 写提交信息，Commit to main，然后 Publish repository。

## 命令行方式

本项目已发布到 https://github.com/hhui53758-cloud/R76S-YOLO-Client 。下列命令适用于创建自己的新仓库；已有本仓库克隆不应重复 init 或添加 origin。源码 ZIP 不包含 `.git` 历史。确认 Git 身份后在仓库根目录运行：

```powershell
git init -b main
git add .
git status --short
git commit -m "Initial R76S YOLO client project"
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

把 YOUR_ACCOUNT/YOUR_REPOSITORY 换成实际仓库。更新已有克隆时使用 git add、git commit、git push，并检查当前 origin。

## 发布 Windows 客户端

按根 README 构建；构建完成后在 GitHub Releases 新建版本，上传 `release/R76S-YOLO-Client-Windows-x64.zip` 和 `release/SHA256SUMS.txt`。发布说明应区分源码包与便携客户端包，并列出支持的设备、模型版本和网络流程。

## 许可与模型资料

第三方来源已保留许可证。原创源码许可尚待作者选择；未添加 MIT 等许可证，以免代替作者授予权利。模型由 Ultralytics YOLO 训练/导出，训练数据授权和相关许可需要作者确认，模型不因附在仓库中就自动继承第三方示例的 Apache-2.0 许可。

仓库 training 目录已补充原始训练脚本、可移植入口、历史参数、逐轮指标与数据来源记录。仍未确认原数据下载版本、数量差额、完整转换校准清单和注意力实验完整记录，因此不声明可逐位复现训练或相关论文对比。数据图片与大安装包应独立核验授权后放 Releases，而不是反复提交到源码历史。
