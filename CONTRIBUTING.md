# 贡献指南

感谢你考虑为 ScreenLogger 贡献代码！以下是一些指导原则，帮助我们更好地协作。

---

## 行为准则

请保持友善和专业的交流氛围。我们欢迎所有形式的贡献，包括但不限于：

- 提交 Bug 报告
- 提出新功能建议
- 改进文档
- 提交代码修复或新功能

---

## 如何贡献

### 报告 Bug

1. 在 [Issues](https://github.com/ws1336/ScreenLogger/issues) 中搜索是否已有相同报告
2. 如果没有，创建新 Issue 并包含：
   - 运行环境（操作系统版本、Python 版本）
   - 复现步骤
   - 预期行为与实际行为
   - 相关日志（如有）
   - 截图（如有）

### 提交新功能建议

1. 先在 Issues 中描述你的想法，等待讨论
2. 明确说明功能的价值和使用场景
3. 如果是 UI 改动，尽量附上草图或 mockup

### 提交代码

1. Fork 本仓库
2. 创建你的特性分支：`git checkout -b feature/my-feature`
3. 提交你的改动
4. 确保代码风格与现有代码一致
5. 确保没有破坏现有功能
6. 推送分支并提交 Pull Request

---

## 开发指南

### 环境搭建

```bash
git clone https://github.com/yourusername/ScreenLogger.git
cd ScreenLogger
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 代码风格

- 遵循 PEP 8
- 函数和类添加 docstring
- 关键逻辑添加行注释
- 使用中文注释（与项目保持一致）

### 提交信息

建议使用清晰简洁的提交信息，例如：

```
feat: 添加导出每日总结为 Markdown 功能
fix: 修复数据迁移后日志路径未更新问题
docs: 更新 README 中的配置说明
refactor: 重构 AI 分析模块的请求路由
```

---

## Pull Request 流程

1. 确保 PR 标题清晰描述改动内容
2. 在 PR 描述中说明改动目的和实现方式
3. 关联相关 Issue（如有）
4. 等待 review，根据反馈修改
5. 合并后你的名字将出现在贡献者名单中

---

## 项目结构参考

```
ScreenLogger/
├── main.py             # 入口文件
├── config/             # 配置管理
├── conf/               # 配置文件
├── capture/            # 屏幕捕获
├── database/           # 数据库层
├── ai/                 # AI 分析
├── storage/            # 存储管理
├── logger/             # 日志系统
├── ui/                 # 用户界面（PySide6）
├── docs/               # 文档
└── assets/             # 资源文件
```

详细架构说明见 [docs/CODE_WIKI.md](docs/CODE_WIKI.md)。

---

再次感谢你的贡献！