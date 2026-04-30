# Book-Grounded Learning Agent

[English](README.en.md)

一个基于 PDF 书籍内容的网页端 AI 学习助手。下面只保留从零配置环境到运行项目的步骤。

## 1. 获取项目

```powershell
git clone <your-repo-url>
cd <your-repo-folder>
```

如果你已经在项目目录里，可以直接跳到下一步。

## 2. 创建 Python 环境

推荐使用 Python 3.12 或更高版本。

使用 Conda：

```powershell
conda create -n book-agent python=3.12
conda activate book-agent
```

或者使用 venv：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. 安装依赖

在项目根目录运行：

```powershell
python -m pip install -e .
```

如果还要运行测试，安装开发依赖：

```powershell
python -m pip install -e ".[dev]"
```

## 4. 启动服务

```powershell
python -m book_agent.main --port 8001
```

如果使用 Conda 直接运行：

```powershell
conda run --no-capture-output -n book-agent python -m book_agent.main --port 8001
```

如果端口被占用，换一个端口：

```powershell
python -m book_agent.main --port 8002
```

## 5. 打开网页

浏览器打开：

```text
http://127.0.0.1:8001/app
```

接口文档：

```text
http://127.0.0.1:8001/docs
```

## 6. 配置大模型

进入网页后，在左侧“模型配置”里填写：

- API Key
- Base URL
- Model
- Reasoning effort，可选
- Thinking type，可选

DeepSeek 示例：

```text
Base URL: https://api.deepseek.com
Model: deepseek-v4-flash
```

也可以填写其他 OpenAI 兼容服务的 Base URL 和模型名。

## 7. 开始学习

1. 在网页端保存模型配置。
2. 在“新建学习”里填写 PDF 路径。
3. 选择学习模式。
4. 点击创建学习进程。
5. 进入学习进程后生成当前课程内容。

PDF 路径必须是运行后端服务的电脑能访问到的本地路径，例如：

```text
D:\books\python.pdf
```

## 8. 可选：运行测试

```powershell
python -m pytest -q
```

可选检查前端脚本：

```powershell
node --check book_agent\web\app.js
```

## License

MIT License. See [LICENSE](LICENSE).
