# 万方科研诚信培训活动页刷课

> 万方科研诚信培训平台（`cx.wanfangdata.com.cn/e-training`）活动页自动刷课工具。
> 检测页面播放进度，**100% 自动切下一课时**，整门课播完**自动切下一门课程**。

Python + Selenium 驱动真实浏览器，不伪造接口数据、不改服务端记录，行为等价于挂着页面看课。

---

## 功能

- **进度检测**：直接读页面上的「播放进度」百分比，到 100% 自动点「下一课」
- **自动切课**：一门课最后一个课时结束后，自动回到活动页进入下一门课，直到全部学完
- **自动跳过**：已学完的课时、随堂测验、PDF 课件自动跳过
- **自动登录**：可填账号密码自动提交；也可留空手动登录，程序检测到登录成功自动接管
- **不中断**：屏蔽切后台暂停事件，保持 `playbackRate` 与静音，窗口不最小化即可
- **两种模式**：兼顾平台「时长进度」判定，或纯按播放进度极速切课
- **断点续刷**：已完成的课时会被识别并跳过，重跑不重复
- **刷课记录**：按课程生成 `record/《课程名》的刷课记录.txt`

## 两种模式

| | 稳过模式（勾选「兼顾时长进度」） | 极速模式（不勾选） |
|---|---|---|
| 倍速 | 锁定 1 倍速 | 1.25 ~ 4 倍 |
| 切课条件 | 播放进度 100% **且** 时长进度 ≥ 阈值 | 播放进度 100% |
| 平台判定 | 正常计入「已学完」 | 可能只记播放进度，不判定完成 |
| 耗时 | ≈ 视频总时长 | ≈ 视频总时长 ÷ 倍速 |

平台「课件完成条件」含两项：**播放进度** 与 **时长进度**。时长按真实墙上时间累计（前端 `learnDuration += (now - enterTime) / 1000`，服务端按 `endTime - learnTime` 记账），倍速无法缩短，所以稳过模式必须 1 倍速播完。

> 先用一门课验证：活动页「已学完 N 个课件」正常增长即说明生效。

## 快速开始

### 方式一：exe（免环境）

下载 [`wanfang-shuake-v1.0.0.exe`](https://github.com/EruClyne0717/wanfang-credit-training-autoplay/releases/latest/download/wanfang-shuake-v1.0.0.exe)（或仓库内 `dist/万方刷课.exe`）：

1. 双击运行，活动地址已预填，按需改
2. 点「开始刷课」，浏览器弹出后登录一次，程序自动接管

### 方式二：源码 + 启动.bat

下载 [`wanfang-shuake-v1.0.0-source.zip`](https://github.com/EruClyne0717/wanfang-credit-training-autoplay/releases/latest/download/wanfang-shuake-v1.0.0-source.zip)，或直接克隆本仓库：

```bash
pip install -r requirements.txt
python main.py        # 或双击 启动.bat
```

需要 Edge 或 Chrome。驱动无需手动下载，Selenium Manager 会自动匹配；也可在界面「驱动路径」手动指定 `msedgedriver.exe` / `chromedriver.exe`。

## 工作原理

页面结构逆向自站点前端 bundle：

| 目标 | 选择器 / 逻辑 |
|---|---|
| 播放进度 | `.progress-count .el-progress-bar__innerText` → `"100%"`，兜底正则 `播放进度：(\d+)%` |
| 时长进度 | `.progress-count` 文本 `时长进度: 1分30秒 / 10分00秒` |
| 下一课 | `#rightBox .progress-count span.next`，末节为 `span.next-no-active` |
| 课时目录 | `#leftBox li.tree_item` 叶子节点，`span.index` 编号、`span.tree-name` 名称、`complete-name` 已学完 |
| 课程列表 | `.course-item` → `.course-name` |
| 学习页 | `/e-training/quality/courselearn?courseId=xxx` |

关键点：**必须点「下一课」而不是直接点目录**——前端在切课时会先 `POST /api/usercenter/insertrecord` 保存进度，直接切目录不触发保存。

## 项目结构

```
.
├── main.py                  # tkinter GUI
├── engine.py                # Selenium 引擎（进度检测 / 切课 / 兜底）
├── 启动.bat                  # 源码版启动脚本
├── requirements.txt
├── config.example.json      # 配置模板（复制为 config.json 使用）
├── 使用说明.md
└── dist/
    └── 万方刷课.exe          # 打包版（PyInstaller onefile）
```

## 常见问题

| 现象 | 处理 |
|---|---|
| 进度不动 | 浏览器窗口别最小化，系统会节流后台标签页 |
| 登录后定位不到课程 | 点「页面诊断」，生成 `debug_manual_*.txt`（地址 / 元素统计 / 页面文字 / HTML） |
| 提示未识别到课程目录 | 可能是直播课，本工具只处理录播视频 |
| 驱动版本不匹配 | 界面「驱动路径」选对应版本的驱动 |
| 活动页解析不到课程 | 程序会自动改从「我的学习」列表页按 `courseId` 抓取 |

## 声明

仅供个人学习与技术研究使用。请遵守所在机构与平台的使用条款，因使用本工具产生的后果由使用者自行承担。

## License

MIT
